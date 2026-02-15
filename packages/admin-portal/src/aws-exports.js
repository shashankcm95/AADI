const redirectUrl = window.location.origin + '/';

const awsConfig = {
    Auth: {
        Cognito: {
            userPoolId: 'us-east-1_SzP2GXCMA',
            userPoolClientId: 'prg3mh9b9ai8trd33s9ls1c',
            loginWith: {
                oauth: {
                    domain: 'arrive-dev-auth-561764227438.auth.us-east-1.amazoncognito.com',
                    scopes: ['openid', 'email', 'profile'],
                    redirectSignIn: [redirectUrl],
                    redirectSignOut: [redirectUrl],
                    responseType: 'code',
                },
            },
        },
    },
};

export const API_BASE_URL = 'https://ph8xe60a2e.execute-api.us-east-1.amazonaws.com';
export const ORDERS_API_URL = 'https://5fnj76yo6i.execute-api.us-east-1.amazonaws.com';

export default awsConfig;
