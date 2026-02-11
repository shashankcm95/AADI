import { StatusBar } from 'expo-status-bar';
import { useState } from 'react';
import { StyleSheet, SafeAreaView, ImageBackground } from 'react-native';
import { NavigationContainer, DefaultTheme } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { theme } from './src/theme';

// Screens
import LoginScreen from './src/screens/LoginScreen';
import RestaurantsScreen from './src/screens/RestaurantsScreen';
import MenuScreen from './src/screens/MenuScreen';
import OrderScreen from './src/screens/OrderScreen';
import TipScreen from './src/screens/TipScreen';
import DepartureScreen from './src/screens/DepartureScreen';

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
  const [currentOrder, setCurrentOrder] = useState<any>(null);

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
            name="Restaurants"
            component={RestaurantsScreen}
            options={{ title: 'Choose Restaurant' }}
          />
          <Stack.Screen
            name="Menu"
            options={({ route }: any) => ({
              title: route.params?.restaurant?.name || 'Menu'
            })}
          >
            {(props) => (
              <MenuScreen
                {...props}
                onOrderPlaced={(order: any) => setCurrentOrder(order)}
              />
            )}
          </Stack.Screen>
          <Stack.Screen
            name="Order"
            component={OrderScreen}
            options={{ title: 'Your Order' }}
          />
          <Stack.Screen
            name="Tip"
            component={TipScreen}
            options={{
              title: 'Thanks for Dining!',
              presentation: 'modal'
            }}
          />
          <Stack.Screen
            name="Departure"
            component={DepartureScreen}
            options={{
              title: 'Perfect Timing',
              presentation: 'modal'
            }}
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
