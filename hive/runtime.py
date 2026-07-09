"""Runtime — agent execution loop with process isolation."""

import asyncio
import json
import time
import types
from concurrent.futures import ProcessPoolExecutor
from hive.config import MAX_AGENTS, AGENT_TIMEOUT
from hive.llm import QwenClient
from hive.tools import TOOLS, execute_tool
from hive.permissions import get_tool_tier, check_dangerous_command, should_auto_allow
from hive.agents.safety_agent import SafetyAgent
from hive.core.agent_state import get_or_create_state


def _run_agent_process(agent_code: str, task: str, context: dict) -> dict:
    """Runs in a separate process. Agent's own memory space."""
    module = types.ModuleType("agent_module")
    module.__dict__["__name__"] = "agent_module"
    try:
        exec(agent_code, module.__dict__)
    except Exception as e:
        return {"error": f"Agent code execution failed: {e}"}

    agent_class = None
    for name in dir(module):
        obj = getattr(module, name)
        if isinstance(obj, type) and hasattr(obj, "execute"):
            agent_class = obj
            break

    if not agent_class:
        return {"error": "No agent class with execute() method found"}

    try:
        agent = agent_class()
        result = agent.execute(task, context)
        return {"result": result}
    except Exception as e:
        return {"error": f"Agent execution failed: {e}"}


MAX_LOOP_ITERATIONS = 20


class AgentRuntime:
    """Manages agent execution with process isolation."""

    def __init__(self, llm: QwenClient):
        self.llm = llm
        self.executor = None
        self.active = {}

    async def run_agent(self, agent_code: str, task: str,
                        context: dict) -> dict:
        """Run agent in separate process."""
        if self.executor is None:
            self.executor = ProcessPoolExecutor(max_workers=MAX_AGENTS)
        loop = asyncio.get_event_loop()
        future = loop.run_in_executor(
            self.executor,
            _run_agent_process,
            agent_code,
            task,
            json.dumps(context),
        )
        try:
            result = await asyncio.wait_for(future, timeout=AGENT_TIMEOUT)
            return result
        except asyncio.TimeoutError:
            return {"error": f"Agent timed out after {AGENT_TIMEOUT}s"}

    async def run_loop(self, session_id: str, messages: list[dict],
                       on_tool_call=None, on_permission=None, on_text=None) -> str:
        """Main agent loop: send to LLM, execute tools, repeat. Uses streaming for fast token display."""
        # Merge MCP tools into TOOLS registry
        try:
            from hive.mcp.bridge import mcp_bridge
            mcp_tools = mcp_bridge.get_hive_tools()
            if mcp_tools:
                from hive.tools import register_mcp_tools
                register_mcp_tools(mcp_tools)
        except ImportError:
            pass

        tools_schema = self.llm.build_tools_schema(TOOLS)
        conversation = list(messages)
        iteration = 0
        agent_state = get_or_create_state("single_agent")
        agent_state.task_started()

        try:
            # First iteration forces tool usage; subsequent iterations use auto
            # so the model can respond with text after getting tool results
            current_tool_choice = "required"
            
            while iteration < MAX_LOOP_ITERATIONS:
                iteration += 1
                
                # Use streaming for fast token-by-token display
                full_content = ""
                tool_calls = []
                
                async for chunk in self.llm.stream(conversation, tools=tools_schema, tool_choice=current_tool_choice):
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    
                    # Stream content token by token
                    if delta.get("content"):
                        token = delta["content"]
                        full_content += token
                        if on_text:
                            await on_text(token)
                    
                    # Collect tool calls
                    if delta.get("tool_calls"):
                        for tc in delta["tool_calls"]:
                            idx = tc.get("index", 0)
                            while len(tool_calls) <= idx:
                                tool_calls.append({"id": "", "function": {"name": "", "arguments": ""}})
                            if tc.get("id"):
                                tool_calls[idx]["id"] = tc["id"]
                            if tc.get("function", {}).get("name"):
                                tool_calls[idx]["function"]["name"] = tc["function"]["name"]
                            if tc.get("function", {}).get("arguments"):
                                tool_calls[idx]["function"]["arguments"] += tc["function"]["arguments"]

                import logging
                _log = logging.getLogger("hive.runtime")
                _log.warning(f"[RUNTIME] Iteration {iteration}: content_len={len(full_content)}, tool_calls={len(tool_calls)}")
                if tool_calls:
                    for tc in tool_calls:
                        _log.warning(f"[RUNTIME] Tool: {tc['function']['name']}({tc['function']['arguments'][:200]})")

                if not tool_calls:
                    agent_state.task_completed(success=True)
                    return full_content or "I did not receive a response from the model."

                # After first tool call, switch to auto so model can respond with text
                current_tool_choice = "auto"

                # When tool_calls present, content should be empty to avoid API issues
                assistant_msg = {"role": "assistant", "content": "", "tool_calls": tool_calls}
                conversation.append(assistant_msg)

                for tc in tool_calls:
                    func = tc.get("function", {})
                    tool_name = func.get("name", "")
                    args_str = func.get("arguments", "{}")
                    try:
                        args = json.loads(args_str)
                    except json.JSONDecodeError:
                        args = {}

                    tier = get_tool_tier(tool_name)
                    target = args.get("path", args.get("url", args.get("command", "")))

                    if tier == "dangerous":
                        decision = "denied"
                        if on_permission:
                            decision = await on_permission(tool_name, target, tier)
                        if decision != "approved":
                            tool_result = {"error": f"Denied: {tool_name}"}
                            conversation.append({
                                "role": "tool",
                                "tool_call_id": tc.get("id", ""),
                                "content": json.dumps(tool_result),
                            })
                            continue

                    if tier in ("moderate", "sensitive"):
                        if not should_auto_allow(tool_name, target):
                            decision = "denied"
                            if on_permission:
                                decision = await on_permission(tool_name, target, tier)
                            if decision != "approved":
                                tool_result = {"error": f"Denied: {tool_name}"}
                                conversation.append({
                                    "role": "tool",
                                    "tool_call_id": tc.get("id", ""),
                                    "content": json.dumps(tool_result),
                                })
                                continue

                    if tool_name == "run_command" and args.get("command"):
                        if check_dangerous_command(args["command"]):
                            tool_result = {"error": f"Blocked dangerous command pattern: {args['command'][:100]}"}
                            conversation.append({
                                "role": "tool",
                                "tool_call_id": tc.get("id", ""),
                                "content": json.dumps(tool_result),
                            })
                            continue

                    safety = SafetyAgent(task_context=str(args))
                    safety_check = await safety.check(str(args))
                    if not safety_check.get("approved", True):
                        tool_result = {"error": f"SafetyAgent blocked: {safety_check.get('reason')}"}
                        conversation.append({
                            "role": "tool",
                            "tool_call_id": tc.get("id", ""),
                            "content": json.dumps(tool_result),
                        })
                        continue

                    if on_tool_call:
                        await on_tool_call(tool_name, args)

                    result = await execute_tool(tool_name, **args)
                    _log.warning(f"[RUNTIME] Tool {tool_name} result: {str(result)[:300]}")

                    conversation.append({
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "content": json.dumps(result),
                    })

            agent_state.task_completed(success=False)
            return f"I reached the maximum number of tool iterations ({MAX_LOOP_ITERATIONS}). Here is what I accomplished so far:\n\n{full_content}" if full_content else "I reached the maximum number of iterations without a final response."
        except Exception as e:
            agent_state.task_completed(success=False)
            raise

    async def run_loop_streaming(self, session_id: str, messages: list[dict],
                                  live=None, dash=None) -> str:
        """Agent loop with streaming output - tokens appear line by line."""
        # Merge MCP tools into TOOLS registry
        try:
            from hive.mcp.bridge import mcp_bridge
            mcp_tools = mcp_bridge.get_hive_tools()
            if mcp_tools:
                from hive.tools import register_mcp_tools
                register_mcp_tools(mcp_tools)
        except ImportError:
            pass

        tools_schema = self.llm.build_tools_schema(TOOLS)
        conversation = list(messages)
        iteration = 0
        agent_state = get_or_create_state("single_agent")
        agent_state.task_started()
        
        # For streaming output
        collected_content = []
        current_response = []
        
        try:
            # First iteration forces tool usage; subsequent iterations use auto
            current_tool_choice = "required"
            
            while iteration < MAX_LOOP_ITERATIONS:
                iteration += 1
                
                # Use streaming
                full_content = ""
                tool_calls = []
                
                async for chunk in self.llm.stream(conversation, tools=tools_schema, tool_choice=current_tool_choice):
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    
                    # Stream content token by token
                    if delta.get("content"):
                        token = delta["content"]
                        full_content += token
                        current_response.append(token)
                        
                        # Print token immediately (line by line effect)
                        import sys
                        sys.stdout.write(token)
                        sys.stdout.flush()
                        
                        # Update dashboard
                        if dash:
                            dash.set_status("thinking")
                
                if not full_content and not tool_calls:
                    # Check for tool calls in final message
                    result = await self.llm.chat(conversation, tools=tools_schema)
                    message = result.get("choices", [{}])[0].get("message") or {}
                    full_content = message.get("content") or ""
                    tool_calls = message.get("tool_calls") or []
                
                if not tool_calls:
                    agent_state.task_completed(success=True)
                    return full_content or "I did not receive a response from the model."
                
                # Handle tool calls
                assistant_msg = {"role": "assistant", "content": full_content, "tool_calls": tool_calls}
                conversation.append(assistant_msg)
                
                for tc in tool_calls:
                    func = tc.get("function", {})
                    tool_name = func.get("name", "")
                    args_str = func.get("arguments", "{}")
                    try:
                        args = json.loads(args_str)
                    except json.JSONDecodeError:
                        args = {}
                    
                    tier = get_tool_tier(tool_name)
                    target = args.get("path", args.get("url", args.get("command", "")))
                    
                    if tier == "dangerous":
                        tool_result = {"error": f"Denied: {tool_name}"}
                        conversation.append({
                            "role": "tool",
                            "tool_call_id": tc.get("id", ""),
                            "content": json.dumps(tool_result),
                        })
                        continue
                    
                    if tool_name == "run_command" and args.get("command"):
                        if check_dangerous_command(args["command"]):
                            tool_result = {"error": f"Blocked dangerous command: {args['command'][:100]}"}
                            conversation.append({
                                "role": "tool",
                                "tool_call_id": tc.get("id", ""),
                                "content": json.dumps(tool_result),
                            })
                            continue
                    
                    # Update dashboard with tool execution
                    if dash:
                        dash.set_status(f"running {tool_name}")
                    
                    # Print tool execution
                    import sys
                    sys.stdout.write(f"\n  [tool] {tool_name}")
                    sys.stdout.flush()
                    
                    result = await execute_tool(tool_name, **args)
                    
                    conversation.append({
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "content": json.dumps(result),
                    })
                
                # After first tool call, switch to auto so model can respond with text
                current_tool_choice = "auto"
            
            agent_state.task_completed(success=False)
            return f"Max iterations reached. {full_content}" if full_content else "Max iterations reached."
        except Exception as e:
            agent_state.task_completed(success=False)
            raise

    def shutdown(self):
        """Shutdown process pool."""
        if self.executor:
            self.executor.shutdown(wait=False)
