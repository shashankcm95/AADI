const awsConfig = {
    Auth: {
        Cognito: {
            userPoolId: 'us-east-1_Ecbkc63rh',
            userPoolClientId: '7o2lsi769hlr63c05krmo5u6rv',
            loginWith: {
                oauth: {
                    domain: 'arrive-dev-auth-561764227438.auth.us-east-1.amazoncognito.com',
                    scopes: ['openid', 'email', 'profile'],
                    redirectSignIn: ['http://localhost:5173/'],
                    redirectSignOut: ['http://localhost:5173/'],
                    responseType: 'code',
                },
            },
        },
    },
    API: {
        REST: {
            arriveApi: {
                endpoint: 'https://f7mqfaxh8i.execute-api.us-east-1.amazonaws.com',
            },
        },
    },
};

export default awsConfig;
