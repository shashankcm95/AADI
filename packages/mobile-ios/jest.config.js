module.exports = {
    preset: 'jest-expo',
    setupFiles: ['<rootDir>/src/setupTests.js'],
    setupFilesAfterEnv: ['@testing-library/jest-native/extend-expect'],
    transformIgnorePatterns: [
        'node_modules/(?!((jest-)?react-native|@react-native(-community)?)|expo(nent)?|@expo(nent)?/.*|@expo-google-fonts/.*|react-navigation|@react-navigation/.*|@unimodules/.*|unimodules|sentry-expo|native-base|react-native-svg|aws-amplify|@aws-amplify|uuid)',
    ],
    moduleFileExtensions: ['ts', 'tsx', 'js', 'jsx'],
};
