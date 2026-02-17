const awsConfig = {
    Auth: {
        Cognito: {
            userPoolId: 'us-east-1_SzP2GXCMA',
            userPoolClientId: 'prg3mh9b9ai8trd33s9ls1c',
            signUpVerificationMethod: 'code',
            loginWith: {
                email: true,
            },
        },
    },
};

// Keep mobile aligned with the same deployed endpoints used by customer web/admin.
export const RESTAURANTS_API_URL = 'https://ph8xe60a2e.execute-api.us-east-1.amazonaws.com';
export const ORDERS_API_URL = 'https://5fnj76yo6i.execute-api.us-east-1.amazonaws.com';

export default awsConfig;
