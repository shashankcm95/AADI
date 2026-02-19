const awsConfig = {
    Auth: {
        Cognito: {
            userPoolId: 'us-east-1_4GtNf4ClO',
            userPoolClientId: '3u3nai0j5gl1r73n1ktciafm9m',
            signUpVerificationMethod: 'code',
            loginWith: {
                email: true,
            },
        },
    },
};

// Keep mobile aligned with the same deployed endpoints used by customer web/admin.
export const RESTAURANTS_API_URL = 'https://5bil2rxq9c.execute-api.us-east-1.amazonaws.com';
export const ORDERS_API_URL = 'https://scscv96kc7.execute-api.us-east-1.amazonaws.com';
export const USERS_API_URL = 'https://pulne3mtk0.execute-api.us-east-1.amazonaws.com';

export default awsConfig;
