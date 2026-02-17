import { brandColors, gradients, overlays, semanticColors } from './colors';
import { screenPadding, spacing } from './spacing';
import { appFontFamily, typeAliases, typography } from './typography';

export const radii = {
    card: 18,
    chip: 999,
    input: 14,
    button: 14,
} as const;

export const shadows = {
    card: {
        shadowColor: '#000',
        shadowOpacity: 0.08,
        shadowRadius: 12,
        shadowOffset: { width: 0, height: 6 },
        elevation: 4,
    },
    hero: {
        shadowColor: '#000',
        shadowOpacity: 0.1,
        shadowRadius: 16,
        shadowOffset: { width: 0, height: 8 },
        elevation: 6,
    },
} as const;

export const theme = {
    colors: {
        white: brandColors.WHITE,
        offWhite: brandColors.OFF_WHITE,
        gold: brandColors.GOLD,
        teal1: brandColors.TEAL_1,
        teal2: brandColors.TEAL_2,
        teal3: brandColors.TEAL_3,
        blue1: brandColors.BLUE_1,
        blue2: brandColors.BLUE_2,
        blue3: brandColors.BLUE_3,
        blue4: brandColors.BLUE_4,
        blue5: brandColors.BLUE_5,
        blue6: brandColors.BLUE_6,
        background: semanticColors.bg.app,
        surface: semanticColors.bg.surface,
        text: semanticColors.text.primary,
        textSecondary: semanticColors.text.secondary,
        border: semanticColors.border.soft,
        overlayTopTint: overlays.topTint,
        glassSurface: overlays.glassSurface,
        glassInput: overlays.glassInput,
        primary: brandColors.BLUE_4,
        accent: brandColors.GOLD,
        textMuted: semanticColors.text.secondary,
        success: '#16A34A',
        error: '#DC2626',
    },
    gradients,
    semantic: semanticColors,
    typography: {
        ...typography,
        ...typeAliases,
    },
    spacing,
    radii,
    shadows,
    screenPadding,
    fontFamily: appFontFamily,
    layout: {
        spacing,
        radius: radii,
        shadows,
        card: {
            backgroundColor: semanticColors.bg.surface,
            borderRadius: radii.card,
            shadowColor: shadows.card.shadowColor,
            shadowOpacity: shadows.card.shadowOpacity,
            shadowRadius: shadows.card.shadowRadius,
            shadowOffset: shadows.card.shadowOffset,
            elevation: shadows.card.elevation,
            padding: spacing.lg,
        },
    },
} as const;

export type AppTheme = typeof theme;
