import type { Variants, Transition } from 'framer-motion'

export const springTransition: Transition = {
  type: 'spring',
  damping: 28,
  stiffness: 280,
}

export const gentleSpring: Transition = {
  type: 'spring',
  damping: 22,
  stiffness: 200,
}

// Page transitions for tab pages
export const pageVariants: Variants = {
  initial: { opacity: 0, y: 10 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -6 },
}

export const pageTransition: Transition = {
  type: 'spring',
  damping: 26,
  stiffness: 260,
}

// Detail pages — slide from right
export const detailVariants: Variants = {
  initial: { x: '100%', opacity: 0.8 },
  animate: { x: 0, opacity: 1 },
  exit: { x: '100%', opacity: 0.8 },
}

export const detailTransition: Transition = {
  type: 'spring',
  damping: 28,
  stiffness: 240,
}

// Staggered list container
export const staggerContainer: Variants = {
  hidden: {},
  show: {
    transition: {
      staggerChildren: 0.04,
      delayChildren: 0.02,
    },
  },
}

// Staggered list item
export const staggerItem: Variants = {
  hidden: { opacity: 0, y: 12 },
  show: {
    opacity: 1,
    y: 0,
    transition: { type: 'spring', damping: 20, stiffness: 200 },
  },
}

// Bottom sheet
export const sheetVariants: Variants = {
  hidden: { y: '100%' },
  visible: { y: 0 },
}

export const sheetTransition: Transition = {
  type: 'spring',
  damping: 28,
  stiffness: 320,
}

// Overlay/backdrop
export const overlayVariants: Variants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1 },
}

// Full-screen player (slide up)
export const playerVariants: Variants = {
  hidden: { y: '100%' },
  visible: { y: 0 },
  exit: { y: '100%' },
}

export const playerTransition: Transition = {
  type: 'spring',
  damping: 30,
  stiffness: 280,
}
