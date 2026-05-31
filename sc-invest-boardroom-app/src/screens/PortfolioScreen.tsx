import React, { useState } from 'react';
import { View, Text, TextInput, Button, StyleSheet, FlatList } from 'react-native';

export default function PortfolioScreen() {
  const [symbol, setSymbol] = useState("");
  const [shares, setShares] = useState("");
  const [cost, setCost] = useState("");
  const [positions, setPositions] = useState<{symbol: string, shares: string, cost: string}[]>([]);

  const addPosition = () => {
    setPositions([...positions, { symbol, shares, cost }]);
    setSymbol("");
    setShares("");
    setCost("");
  };

  const savePositions = () => {
    // API call to PUT /api/portfolios/{id}/positions
    console.log("Saving Positions...", positions);
  };

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Manage Positions</Text>
      <View style={styles.form}>
        <TextInput placeholder="Symbol" value={symbol} onChangeText={setSymbol} style={styles.input} placeholderTextColor="#a1a1aa" />
        <TextInput placeholder="Shares" value={shares} onChangeText={setShares} style={styles.input} keyboardType="numeric" placeholderTextColor="#a1a1aa" />
        <TextInput placeholder="Cost Basis" value={cost} onChangeText={setCost} style={styles.input} keyboardType="numeric" placeholderTextColor="#a1a1aa" />
        <Button title="Add" onPress={addPosition} color="#95b8a2" />
      </View>

      <FlatList 
        data={positions}
        keyExtractor={(item, index) => index.toString()}
        renderItem={({item}) => (
          <Text style={styles.item}>{item.symbol} - {item.shares} shares @ ${item.cost}</Text>
        )}
      />

      <Button title="Save All to Cloud" onPress={savePositions} color="#95b8a2" />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#121212',
    padding: 20,
  },
  title: {
    fontSize: 20,
    color: '#f4f4f5',
    marginBottom: 10,
  },
  form: {
    flexDirection: 'row',
    marginBottom: 20,
  },
  input: {
    backgroundColor: '#1e1e1e',
    color: '#fff',
    padding: 10,
    marginRight: 5,
    flex: 1,
    borderRadius: 5,
  },
  item: {
    color: '#a1a1aa',
    padding: 10,
    borderBottomWidth: 1,
    borderBottomColor: '#333',
  }
});
