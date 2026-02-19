const redirectUrl = window.location.origin + '/';

const awsConfig = {
    Auth: {
        Cognito: {
            userPoolId: 'us-east-1_4GtNf4ClO',
            userPoolClientId: '3u3nai0j5gl1r73n1ktciafm9m',
            loginWith: {
                oauth: {
                    domain: 'arrive-fresh-auth-561764227438.auth.us-east-1.amazoncognito.com',
                    scopes: ['openid', 'email', 'profile'],
                    redirectSignIn: [redirectUrl],
                    redirectSignOut: [redirectUrl],
                    responseType: 'code',
                },
            },
        },
    },
};

export const API_BASE_URL = 'https://5bil2rxq9c.execute-api.us-east-1.amazonaws.com';
export const ORDERS_API_URL = 'https://scscv96kc7.execute-api.us-east-1.amazonaws.com';

export default awsConfig;
