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
                    redirectSignIn: [window.location.origin + '/'],
                    redirectSignOut: [window.location.origin + '/'],
                    responseType: 'code',
                },
            },
        },
    }
};

export default awsConfig;
