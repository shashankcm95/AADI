import { ViewStyle, TextStyle, ImageStyle } from 'react-native';

export const theme = {
    colors: {
        // Brand Palette
        white: '#FEFEFE',
        offWhite: '#F7FBFA',
        gold: '#E0DECD',

        // Teals
        teal1: '#73C3C5',
        teal2: '#68B1C1',
        teal3: '#53B8BA',

        // Blues
        blue1: '#6DA3B4',
        blue2: '#4B99BA',
        blue3: '#237CB5',
        blue4: '#2162BA', // Primary Action
        blue5: '#2A65BE',
        blue6: '#2857C0',

        // Semantic
        background: '#F7FBFA',
        surface: '#FEFEFE',
        text: '#2162BA', // Primary Text (Blue 4)
        textSecondary: '#546E7A',
        border: 'rgba(33,98,186,0.12)',

        // Legacy support (keep existing keys mapped to new values where possible)
        primary: '#2162BA',
        accent: '#E0DECD',
        textMuted: '#546E7A',
        error: '#ef4444',
        success: '#22c55e',
    },
    typography: {
        header: {
            fontSize: 28,
            fontWeight: '700' as const,
            color: '#2162BA',
            fontFamily: 'System',
        },
        subHeader: {
            fontSize: 22,
            fontWeight: '700' as const,
            color: '#2162BA',
        },
        cardTitle: { // New H3
            fontSize: 18,
            fontWeight: '700' as const,
            color: '#2162BA',
        },
        body: {
            fontSize: 16,
            color: '#546E7A',
        },
        caption: {
            fontSize: 12,
            fontWeight: '500' as const,
            color: '#546E7A',
        },
    },
    layout: {
        spacing: {
            xs: 4, sm: 8, md: 12, lg: 16, xl: 20, xxl: 24, xxxl: 32
        },
        radius: {
            card: 18,
            chip: 999,
            input: 14,
            button: 14,
        },
        shadows: {
            card: {
                shadowColor: '#000',
                shadowOffset: { width: 0, height: 6 },
                shadowOpacity: 0.08,
                shadowRadius: 12,
                elevation: 4,
            },
            hero: {
                shadowColor: '#000',
                shadowOffset: { width: 0, height: 8 },
                shadowOpacity: 0.10,
                shadowRadius: 16,
                elevation: 6,
            }
        },
        card: {
            backgroundColor: '#FEFEFE',
            borderRadius: 18,
            shadowColor: '#000',
            shadowOffset: { width: 0, height: 6 },
            shadowOpacity: 0.08,
            shadowRadius: 12,
            elevation: 4,
        }
    }
};
