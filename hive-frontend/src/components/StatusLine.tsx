import { Box, Text } from 'ink';

const STATUS_STYLES: Record<string, { color: string; icon: string }> = {
  idle:        { color: 'dim',      icon: '-' },
  routing:     { color: 'yellow',   icon: '>' },
  spawning:    { color: 'yellow',   icon: '*' },
  decomposing: { color: 'yellow',   icon: '#' },
  thinking:    { color: 'brightYellow', icon: '~' },
  running:     { color: 'green',    icon: '+' },
  synthesizing:{ color: 'cyan',     icon: '=' },
  debating:    { color: 'magenta',  icon: '!' },
  rejected:    { color: 'red',      icon: 'x' },
  cleanup:     { color: 'dim',      icon: '-' },
  done:        { color: 'green',    icon: '+' },
  error:       { color: 'red',      icon: '!' },
};

const BEE_ANIM = ['(o.o)', '(O.O)', '(o.o)', '(@_@)'];

interface StatusLineProps {
  status: string;
  mode: string;
  elapsed: string;
  budgetSpent: number;
  budgetTotal: number;
  beeFrame: number;
}

export function StatusLine({ status, mode, elapsed, budgetSpent, budgetTotal, beeFrame }: StatusLineProps) {
  const remaining = budgetTotal - budgetSpent;
  const budgetColor = remaining > 500 ? 'green' : remaining > 200 ? 'yellow' : 'red';
  const style = STATUS_STYLES[status] || STATUS_STYLES.idle;
  const bee = BEE_ANIM[beeFrame % BEE_ANIM.length];

  return (
    <Box borderStyle="round" borderColor="yellow" paddingX={1} marginBottom={1}>
      <Text color="yellow"> {bee} </Text>
      <Text> </Text>
      <Text bold color={style.color}>{style.icon} {status.toUpperCase()}</Text>
      <Text> </Text>
      <Text color="dim">|</Text>
      <Text> </Text>
      <Text color="dim">mode:</Text>
      <Text color={mode === 'auto' ? 'green' : 'yellow'} bold> {mode.toUpperCase()}</Text>
      <Text> </Text>
      <Text color="dim">|</Text>
      <Text> </Text>
      <Text color="yellow">{elapsed}</Text>
      <Text> </Text>
      <Text color="dim">|</Text>
      <Text> </Text>
      <Text color={budgetColor}>{remaining} cr</Text>
    </Box>
  );
}
