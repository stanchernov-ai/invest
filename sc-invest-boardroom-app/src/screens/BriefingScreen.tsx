import React from 'react';
import { View, StyleSheet } from 'react-native';
import { WebView } from 'react-native-webview';

export default function BriefingScreen() {
  const briefingUrl = "https://example.com/api/runs/latest/briefing"; // Mock URL

  return (
    <View style={styles.container}>
      <WebView 
        source={{ uri: briefingUrl }} 
        style={styles.webview}
        // In reality, this would pass the MSAL Bearer token in headers or load a pre-signed blob URL
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#121212',
  },
  webview: {
    flex: 1,
    backgroundColor: 'transparent',
  }
});
