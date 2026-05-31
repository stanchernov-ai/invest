import React, { useState } from 'react';
import { View, Text, TextInput, Button, StyleSheet, ScrollView } from 'react-native';

export default function ProfileScreen() {
  const [riskSlider, setRiskSlider] = useState("75");
  const [convictionSlider, setConvictionSlider] = useState("80");
  const [benchmark, setBenchmark] = useState("NASDAQ");

  const saveProfile = () => {
    // API call to PATCH /api/me
    console.log("Saving Profile...", { riskSlider, convictionSlider, benchmark });
  };

  return (
    <ScrollView style={styles.container}>
      <Text style={styles.label}>Risk Slider (0-100)</Text>
      <TextInput style={styles.input} value={riskSlider} onChangeText={setRiskSlider} keyboardType="numeric" />

      <Text style={styles.label}>Conviction Slider (0-100)</Text>
      <TextInput style={styles.input} value={convictionSlider} onChangeText={setConvictionSlider} keyboardType="numeric" />

      <Text style={styles.label}>Benchmark</Text>
      <TextInput style={styles.input} value={benchmark} onChangeText={setBenchmark} />

      <Button title="Save Profile" onPress={saveProfile} color="#95b8a2" />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#121212',
    padding: 20,
  },
  label: {
    color: '#f4f4f5',
    marginBottom: 5,
    marginTop: 15,
  },
  input: {
    backgroundColor: '#1e1e1e',
    color: '#fff',
    padding: 10,
    borderRadius: 5,
  }
});
