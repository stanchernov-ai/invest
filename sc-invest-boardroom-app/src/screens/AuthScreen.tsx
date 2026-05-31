import React from 'react';
import { View, Text, Button, StyleSheet } from 'react-native';

export default function AuthScreen() {
  const handleLogin = () => {
    // MSAL login logic here
    console.log("Login with Entra External ID");
  };

  return (
    <View style={styles.container}>
      <Text style={styles.title}>SC Invest Boardroom</Text>
      <Text style={styles.subtitle}>Sign in with your Microsoft Entra account</Text>
      <Button title="Login" onPress={handleLogin} color="#95b8a2" />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#121212',
    alignItems: 'center',
    justifyContent: 'center',
  },
  title: {
    fontSize: 24,
    color: '#f4f4f5',
    marginBottom: 10,
  },
  subtitle: {
    fontSize: 16,
    color: '#a1a1aa',
    marginBottom: 20,
  }
});
