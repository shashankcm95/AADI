jest.mock('@react-native-async-storage/async-storage', () =>
    require('@react-native-async-storage/async-storage/jest/async-storage-mock')
);

jest.mock('react-native-safe-area-context', () => ({
    SafeAreaView: ({ children }) => children,
    useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }),
}));

jest.mock('aws-amplify', () => ({
    Amplify: {
        configure: jest.fn(),
    },
}));

jest.mock('aws-amplify/auth', () => ({
    fetchAuthSession: jest.fn().mockResolvedValue({
        tokens: { idToken: { toString: () => 'mock-token' } }
    }),
}));
