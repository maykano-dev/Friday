import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import { connectWsBridge } from './store/zaraStore';

// Connect to Python WS bridge immediately
connectWsBridge();

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(<App />);
