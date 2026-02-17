export const brandColors = {
    WHITE: '#FEFEFE',
    OFF_WHITE: '#F7FBFA',
    GOLD: '#E0DECD',
    TEAL_1: '#73C3C5',
    TEAL_2: '#68B1C1',
    TEAL_3: '#53B8BA',
    BLUE_1: '#6DA3B4',
    BLUE_2: '#4B99BA',
    BLUE_3: '#237CB5',
    BLUE_4: '#2162BA',
    BLUE_5: '#2A65BE',
    BLUE_6: '#2857C0',
} as const;

export const semanticColors = {
    bg: {
        app: '#F7FBFA',
        surface: '#FEFEFE',
    },
    text: {
        primary: '#2162BA',
        secondary: '#546E7A',
    },
    border: {
        soft: 'rgba(33,98,186,0.12)',
    },
    accent: {
        gold: '#E0DECD',
    },
} as const;

export const gradients = {
    primary: [brandColors.TEAL_1, brandColors.BLUE_4] as const,
    secondary: [brandColors.TEAL_2, brandColors.BLUE_2] as const,
} as const;

export const overlays = {
    topTint: 'rgba(115,195,197,0.12)',
    glassSurface: 'rgba(255,255,255,0.82)',
    glassInput: 'rgba(255,255,255,0.85)',
} as const;
