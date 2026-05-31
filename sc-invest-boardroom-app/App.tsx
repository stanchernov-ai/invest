import React from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import BriefingScreen from './src/screens/BriefingScreen';
import PortfolioScreen from './src/screens/PortfolioScreen';
import ProfileScreen from './src/screens/ProfileScreen';
import AuthScreen from './src/screens/AuthScreen';

const Tab = createBottomTabNavigator();

// Simplistic auth state simulation for GTM structure
const isAuthenticated = true;

export default function App() {
  if (!isAuthenticated) {
    return (
      <SafeAreaProvider>
        <NavigationContainer>
          <AuthScreen />
        </NavigationContainer>
      </SafeAreaProvider>
    );
  }

  return (
    <SafeAreaProvider>
      <NavigationContainer>
        <Tab.Navigator screenOptions={{ 
            headerShown: true,
            tabBarActiveTintColor: '#95b8a2',
            tabBarStyle: { backgroundColor: '#1e1e1e' },
            headerStyle: { backgroundColor: '#121212' },
            headerTintColor: '#fff'
        }}>
          <Tab.Screen name="Briefing" component={BriefingScreen} />
          <Tab.Screen name="Portfolio" component={PortfolioScreen} />
          <Tab.Screen name="Profile" component={ProfileScreen} />
        </Tab.Navigator>
      </NavigationContainer>
    </SafeAreaProvider>
  );
}
