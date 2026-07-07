import {
  Button as ChakraButton,
  IconButton as ChakraIconButton,
  type ButtonProps as ChakraButtonProps,
  type IconButtonProps as ChakraIconButtonProps,
} from '@chakra-ui/react';

export type UiButtonVariant = 'solid' | 'outline' | 'ghost' | 'nav' | 'tab' | 'danger' | 'rowAction' | 'plainIcon';

const buttonVariants: Record<UiButtonVariant, ChakraButtonProps> = {
  solid: {
    bg: 'accent.default',
    color: 'var(--accent-contrast)',
    borderColor: 'accent.default',
    _hover: { bg: 'accent.muted' },
  },
  outline: {
    bg: 'bg.surface',
    color: 'fg.default',
    borderColor: 'border.strong',
    _hover: { bg: 'bg.subtle' },
  },
  ghost: {
    bg: 'transparent',
    color: 'fg.default',
    borderColor: 'transparent',
    _hover: { bg: 'bg.subtle' },
  },
  nav: {
    justifyContent: 'flex-start',
    width: '100%',
    bg: 'transparent',
    color: 'fg.default',
    borderColor: 'transparent',
    fontWeight: '600',
    _hover: { bg: 'bg.subtle' },
    _active: { bg: 'bg.muted' },
  },
  tab: {
    bg: 'transparent',
    color: 'fg.muted',
    borderColor: 'transparent',
    fontWeight: '600',
    _hover: { color: 'fg.default', bg: 'bg.subtle' },
    _active: { color: 'fg.default', bg: 'bg.muted' },
  },
  danger: {
    bg: 'danger.subtle',
    color: 'danger.default',
    borderColor: 'danger.border',
    _hover: { bg: 'danger.subtle' },
  },
  rowAction: {
    bg: 'transparent',
    color: 'fg.muted',
    borderColor: 'transparent',
    fontSize: 'sm',
    fontWeight: '600',
    _hover: { color: 'fg.default', bg: 'bg.subtle' },
  },
  plainIcon: {
    bg: 'transparent',
    color: 'fg.default',
    borderColor: 'transparent',
    p: '0',
    minW: 'auto',
    _hover: { bg: 'transparent', color: 'fg.default' },
  },
};

export type UiButtonProps = Omit<ChakraButtonProps, 'variant'> & {
  uiVariant?: UiButtonVariant;
};

export function Button({ uiVariant = 'outline', ...props }: UiButtonProps) {
  return <ChakraButton borderWidth="1px" borderRadius="0" size="sm" {...buttonVariants[uiVariant]} {...props} />;
}

export type UiIconButtonProps = Omit<ChakraIconButtonProps, 'variant'> & {
  uiVariant?: UiButtonVariant;
};

export function IconButton({ uiVariant = 'plainIcon', ...props }: UiIconButtonProps) {
  return <ChakraIconButton borderWidth="1px" borderRadius="0" size="sm" {...buttonVariants[uiVariant]} {...props} />;
}
