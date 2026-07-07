import { Box, Text } from 'ink';

interface Message {
  id: string;
  role: string;
  content: string;
}

interface MessageLogProps {
  messages: Message[];
  processing: boolean;
  streamText: string;
  toolCalls: Array<{ tool: string; args: Record<string, unknown> }>;
}

export function MessageLog({ messages, processing, streamText, toolCalls }: MessageLogProps) {
  return (
    <Box flexDirection="column">
      {messages.length === 0 && !processing && (
        <Box marginTop={1}>
          <Text color="dim">  Ask me anything... (e.g. "list files", "write a script")</Text>
        </Box>
      )}

      {messages.map((msg) => (
        <Box key={msg.id} flexDirection="column" marginBottom={1}>
          {msg.role === 'user' && (
            <Text>
              <Text color="yellow" bold> you {'>'} </Text>
              <Text color="white">{msg.content}</Text>
            </Text>
          )}
          {msg.role === 'assistant' && (
            <Text>
              <Text color="brightYellow" bold> hive {'>'} </Text>
              <Text color="white">{msg.content}</Text>
            </Text>
          )}
          {msg.role === 'error' && (
            <Text>
              <Text color="red" bold> err {'>'} </Text>
              <Text color="red">{msg.content}</Text>
            </Text>
          )}
        </Box>
      ))}

      {processing && toolCalls.length > 0 && (
        <Box flexDirection="column" marginBottom={1}>
          {toolCalls.map((tc, i) => (
            <Text key={i} color="cyan">
              {'  '}~ {tc.tool}({Object.keys(tc.args).join(', ')})
            </Text>
          ))}
        </Box>
      )}

      {processing && streamText && (
        <Box flexDirection="column" marginBottom={1}>
          <Text color="brightYellow" bold> hive {'>'} </Text>
          <Text color="white">{streamText}</Text>
        </Box>
      )}

      {processing && !streamText && toolCalls.length === 0 && (
        <Box>
          <Text color="yellow">  ... thinking</Text>
        </Box>
      )}
    </Box>
  );
}
