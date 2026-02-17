import { Platform } from 'react-native';

const fontFamily = Platform.OS === 'ios' ? 'System' : 'Roboto';

export const typography = {
    h1: {
        fontFamily,
        fontSize: 28,
        lineHeight: 34,
        fontWeight: '700' as const,
    },
    h2: {
        fontFamily,
        fontSize: 22,
        lineHeight: 28,
        fontWeight: '700' as const,
    },
    h3: {
        fontFamily,
        fontSize: 18,
        lineHeight: 24,
        fontWeight: '700' as const,
    },
    body: {
        fontFamily,
        fontSize: 16,
        lineHeight: 22,
        fontWeight: '400' as const,
    },
    bodySm: {
        fontFamily,
        fontSize: 14,
        lineHeight: 20,
        fontWeight: '400' as const,
    },
    caption: {
        fontFamily,
        fontSize: 12,
        lineHeight: 16,
        fontWeight: '500' as const,
    },
} as const;

export const typeAliases = {
    header: typography.h1,
    subHeader: typography.h2,
    cardTitle: typography.h3,
} as const;

export const appFontFamily = fontFamily;
