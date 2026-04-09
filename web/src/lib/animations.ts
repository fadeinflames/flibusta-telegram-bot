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

// Page transitions for tab pages — fast tween to avoid spring jank
export const pageVariants: Variants = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0 },
}

export const pageTransition: Transition = {
  duration: 0.15,
  ease: 'easeOut',
}

// Detail pages — slide from right, fast tween
export const detailVariants: Variants = {
  initial: { x: '100%', opacity: 0.9 },
  animate: { x: 0, opacity: 1 },
  exit: { x: '100%', opacity: 0.9 },
}

export const detailTransition: Transition = {
  duration: 0.25,
  ease: [0.32, 0.72, 0, 1],
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
  hidden: { opacity: 0, y: 8 },
  show: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.2, ease: 'easeOut' },
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
