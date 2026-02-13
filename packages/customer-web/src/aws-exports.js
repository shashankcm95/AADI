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
                    redirectSignIn: [window.location.origin + '/'],
                    redirectSignOut: [window.location.origin + '/'],
                    responseType: 'code',
                },
            },
        },
    }
};

export default awsConfig;
