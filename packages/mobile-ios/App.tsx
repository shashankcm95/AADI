import { StatusBar } from 'expo-status-bar';
import { StyleSheet, SafeAreaView } from 'react-native';
import { NavigationContainer, DefaultTheme } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { theme } from './src/theme';

// Screens
import LoginScreen from './src/screens/LoginScreen';
import { HomeScreen } from './src/screens/HomeScreen';
import MenuScreen from './src/screens/MenuScreen';
import OrderScreen from './src/screens/OrderScreen';

const Stack = createNativeStackNavigator();

const navTheme = {
    ...DefaultTheme,
    colors: {
        ...DefaultTheme.colors,
        background: theme.colors.background,
        primary: theme.colors.primary,
        card: theme.colors.background, // Match header to background for clean look
        text: theme.colors.primary,
    },
};

export default function App() {
    return (
        <NavigationContainer theme={navTheme}>
            <SafeAreaView style={styles.container}>
                <StatusBar style="dark" />
                <Stack.Navigator
                    screenOptions={{
                        headerStyle: { backgroundColor: theme.colors.background },
                        headerTintColor: theme.colors.primary,
                        headerTitleStyle: { fontWeight: 'bold', fontFamily: 'System', fontSize: 20 },
                        headerShadowVisible: false, // Clean header
                        contentStyle: { backgroundColor: theme.colors.background },
                    }}
                >
                    <Stack.Screen
                        name="Login"
                        component={LoginScreen}
                        options={{ title: 'AADI', headerShown: false }}
                    />
                    <Stack.Screen
                        name="Home"
                        component={HomeScreen}
                        options={{ headerShown: false }}
                    />
                    <Stack.Screen
                        name="Menu"
                        component={MenuScreen}
                        options={({ route }: any) => ({
                            title: route.params?.restaurant?.name || 'Menu',
                        })}
                    />
                    <Stack.Screen
                        name="Order"
                        component={OrderScreen}
                        options={{ title: 'Your Order' }}
                    />
                </Stack.Navigator>
            </SafeAreaView>
        </NavigationContainer>
    );
}

const styles = StyleSheet.create({
    container: {
        flex: 1,
        backgroundColor: theme.colors.background,
    },
});
