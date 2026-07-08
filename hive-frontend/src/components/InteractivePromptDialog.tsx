import { Box, Text, useInput } from 'ink';
import { useMemo, useState } from 'react';

import type { InteractivePromptRequest } from '../types.js';

interface InteractivePromptDialogProps {
  prompt: InteractivePromptRequest;
  onDecision: (requestId: string, result: unknown) => void;
}

export function InteractivePromptDialog({ prompt, onDecision }: InteractivePromptDialogProps) {
  const [code, setCode] = useState('');
  const [approved, setApproved] = useState(false);

  const title = useMemo(() => {
    if (prompt.kind === '2fa') return 'Verification Code Required';
    if (prompt.kind === 'checkout_confirm') return 'Confirm Purchase';
    if (prompt.kind === 'captcha_handoff') return 'CAPTCHA — Human Required';
    return 'Interactive Prompt';
  }, [prompt.kind]);

  useInput((keyInput, key) => {
    if (key.escape) {
      if (prompt.kind === '2fa') onDecision(prompt.request_id, null);
      else onDecision(prompt.request_id, false);
      return;
    }

    if (key.return) {
      if (prompt.kind === '2fa') {
        const trimmed = code.trim();
        if (trimmed) onDecision(prompt.request_id, trimmed);
        return;
      }
      if (prompt.kind === 'checkout_confirm') {
        onDecision(prompt.request_id, approved);
        return;
      }
      if (prompt.kind === 'captcha_handoff') {
        onDecision(prompt.request_id, true);
        return;
      }
    }

    if (prompt.kind === 'checkout_confirm') {
      if (keyInput === 'y') setApproved(true);
      if (keyInput === 'n') setApproved(false);
      return;
    }

    if (prompt.kind === '2fa') {
      // Accept digits only
      if (keyInput && /^[0-9]$/.test(keyInput)) {
        if (code.length < 8) setCode(prev => prev + keyInput);
      }
      if (key.backspace || keyInput === '\b') {
        setCode(prev => prev.slice(0, -1));
      }
    }
  });

  return (
    <Box
      flexDirection="column"
      borderStyle="round"
      borderColor="cyan"
      paddingX={1}
      marginTop={1}
    >
      <Text color="cyan" bold>{title}</Text>
      <Box>
        {prompt.site && <Text color="white">Site: {prompt.site}</Text>}
        {prompt.message && <Text color="dim">{prompt.message}</Text>}
        {prompt.kind === 'checkout_confirm' && (
          <Text color="white">
            {prompt.merchant} · Amount: ${typeof prompt.amount === 'number' ? prompt.amount.toFixed(2) : 'unknown'}
          </Text>
        )}
      </Box>
      <Box>
        {prompt.kind === '2fa' && (
          <Text>
            <Text color="yellow" bold>Code:</Text> <Text color="white">{code ? '*'.repeat(code.length) : ''}</Text>
            <Text color="dim">  (type digits, Enter to submit)</Text>
          </Text>
        )}
        {prompt.kind === 'checkout_confirm' && (
          <Text>
            <Text color={approved ? 'green' : 'dim'} bold> [Y] Confirm </Text>
            <Text> </Text>
            <Text color={!approved ? 'red' : 'dim'} bold> [N] Cancel </Text>
          </Text>
        )}
        {prompt.kind === 'captcha_handoff' && (
          <Text color="dim">Solve the CAPTCHA in the browser window, then press Enter here.</Text>
        )}
      </Box>
    </Box>
  );
}

