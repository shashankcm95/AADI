import React from 'react';
import { fireEvent, render, waitFor } from '@testing-library/react-native';
import LoginScreen from '../LoginScreen';
import { fetchAuthSession, signIn } from 'aws-amplify/auth';

jest.mock('aws-amplify/auth', () => ({
    confirmResetPassword: jest.fn(),
    confirmSignUp: jest.fn(),
    fetchAuthSession: jest.fn(),
    resendSignUpCode: jest.fn(),
    resetPassword: jest.fn(),
    signIn: jest.fn(),
    signOut: jest.fn(),
    signUp: jest.fn(),
}));

describe('LoginScreen', () => {
    const navigation = {
        navigate: jest.fn(),
        reset: jest.fn(),
    };

    beforeEach(() => {
        jest.clearAllMocks();
    });

    it('resets to Home after successful sign-in', async () => {
        (fetchAuthSession as jest.Mock)
            .mockResolvedValueOnce({ tokens: {} }) // initial session check on mount
            .mockResolvedValue({
                tokens: {
                    idToken: {
                        payload: { email: 'jane@example.com' },
                    },
                },
            });

        (signIn as jest.Mock).mockResolvedValue({
            isSignedIn: true,
            nextStep: { signInStep: 'DONE' },
        });

        const { getByPlaceholderText, getByText } = render(
            <LoginScreen navigation={navigation as any} />
        );

        fireEvent.changeText(getByPlaceholderText('user@example.com'), 'jane@example.com');
        fireEvent.changeText(getByPlaceholderText('••••••••'), 'hunter2');
        fireEvent.press(getByText('Sign In'));

        await waitFor(() => {
            expect(navigation.reset).toHaveBeenCalledWith({
                index: 0,
                routes: [
                    {
                        name: 'Home',
                        params: { customerName: 'jane' },
                    },
                ],
            });
        });
    });
});
