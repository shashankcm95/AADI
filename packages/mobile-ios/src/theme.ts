import { ViewStyle, TextStyle, ImageStyle } from 'react-native';

export const theme = {
    colors: {
        background: '#FDFAF6', // Cream
        primary: '#00695c', // Emerald
        text: '#1E293B', // Dark Slate
        textMuted: '#64748B',
        accent: '#D4AF37', // Gold
        teal: '#00C9A7',
        coral: '#FFCCBC',
        surface: 'rgba(255, 255, 255, 0.9)',
        surfaceHighlight: '#ffffff',
        error: '#ef4444',
        success: '#22c55e',
        cardShadow: 'rgba(0, 105, 92, 0.15)',
    },
    typography: {
        // In React Native, we might need to load custom fonts or fall back to system serif/sans
        header: {
            fontSize: 32,
            fontWeight: '600' as const,
            color: '#00695c',
            fontFamily: 'System', // Ideally 'PlayfairDisplay' if linked
        },
        subHeader: {
            fontSize: 24,
            fontWeight: '600' as const,
            color: '#1E293B',
        },
        body: {
            fontSize: 16,
            color: '#1E293B',
        },
        caption: {
            fontSize: 14,
            color: '#64748B',
        },
    },
    layout: {
        card: {
            backgroundColor: 'rgba(255, 255, 255, 0.8)',
            borderRadius: 24,
            padding: 20,
            shadowColor: 'rgba(0, 105, 92, 0.15)',
            shadowOffset: { width: 0, height: 10 },
            shadowOpacity: 0.1,
            shadowRadius: 20,
            elevation: 5, // Android
            marginBottom: 20,
            borderWidth: 1,
            borderColor: 'rgba(255,255,255,0.6)',
        } as ViewStyle,
        organicBorder: {
            borderRadius: 24, // React Native doesn't support the crazy 4-value radius syntax easily without SVG
            borderTopRightRadius: 40,
            borderBottomLeftRadius: 30,
        } as ViewStyle,
        container: {
            flex: 1,
            backgroundColor: '#FDFAF6',
            paddingHorizontal: 20,
        } as ViewStyle,
    },
    components: {
        buttonPrimary: {
            backgroundColor: '#00695c',
            paddingVertical: 16,
            paddingHorizontal: 32,
            borderRadius: 50,
            alignItems: 'center',
            shadowColor: '#000',
            shadowOffset: { width: 0, height: 4 },
            shadowOpacity: 0.2,
            shadowRadius: 8,
        } as ViewStyle,
        buttonText: {
            color: '#ffffff',
            fontSize: 18,
            fontWeight: '700' as const,
        } as TextStyle,
        input: {
            backgroundColor: 'rgba(255,255,255,0.8)',
            borderRadius: 12,
            padding: 16,
            borderWidth: 1,
            borderColor: '#ddd',
            marginBottom: 16,
            fontSize: 16,
            color: '#1E293B',
        } as TextStyle,
    }
};
