import { useState, useCallback, useRef } from 'react';
import { Box, Text, useInput } from 'ink';

interface PermissionDialogProps {
  tool: string;
  target: string;
  tier: string;
  requestId: string;
  onDecision: (requestId: string, decision: string) => void;
}

export function PermissionDialog({ tool, target, tier, requestId, onDecision }: PermissionDialogProps) {
  const [selected, setSelected] = useState<'approve' | 'deny'>('approve');
  const selectedRef = useRef(selected);
  selectedRef.current = selected;

  const decide = useCallback((decision: string) => {
    onDecision(requestId, decision);
  }, [requestId, onDecision]);

  useInput((keyInput, key) => {
    if (key.return) {
      decide(selectedRef.current);
      return;
    }
    if (key.leftArrow || key.rightArrow || keyInput === 'y' || keyInput === 'n') {
      if (keyInput === 'y') { decide('approved'); return; }
      if (keyInput === 'n') { decide('denied'); return; }
      setSelected(prev => prev === 'approve' ? 'deny' : 'approve');
    }
    if (key.escape) { decide('denied'); }
  });

  return (
    <Box flexDirection="column" borderStyle="round" borderColor="yellow" paddingX={1} marginTop={1}>
      <Text color="yellow" bold> Permission Request </Text>
      <Text> </Text>
      <Text color="white">Tool: {tool}</Text>
      {target && <Text color="dim">Target: {target}</Text>}
      <Text color="yellow">Tier: {tier}</Text>
      <Text> </Text>
      <Text>
        <Text color={selected === 'approve' ? 'green' : 'dim'} bold> [Y] Approve </Text>
        <Text>  </Text>
        <Text color={selected === 'deny' ? 'red' : 'dim'} bold> [N] Deny </Text>
      </Text>
      <Text color="dim"> Enter to confirm, arrows to toggle</Text>
    </Box>
  );
}
