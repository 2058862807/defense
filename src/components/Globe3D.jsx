import React, { useRef, useMemo, useEffect, useState } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { OrbitControls, Html } from '@react-three/drei';
import * as THREE from 'three';

// Convert Lat/Lng to Vector3 on sphere surface
function latLngToVector3(lat, lng, radius) {
  const phi = (90 - lat) * (Math.PI / 180);
  const theta = (lng + 180) * (Math.PI / 180);
  const x = -radius * Math.sin(phi) * Math.cos(theta);
  const y = radius * Math.cos(phi);
  const z = radius * Math.sin(phi) * Math.sin(theta);
  return new THREE.Vector3(x, y, z);
}

const FINANCIAL_HUBS = [
  { name: 'NYC (Fedwire)', lat: 40.7128, lng: -74.006, code: 'USD' },
  { name: 'London (CHAPS)', lat: 51.5074, lng: -0.1278, code: 'GBP' },
  { name: 'Hong Kong (HKD)', lat: 22.3193, lng: 114.1694, code: 'HKD' },
  { name: 'Singapore (MAS)', lat: 1.3521, lng: 103.8198, code: 'SGD' },
  { name: 'Tokyo (BOJ)', lat: 35.6762, lng: 139.6503, code: 'JPY' },
  { name: 'Zurich (SIX)', lat: 47.3769, lng: 8.5417, code: 'CHF' },
  { name: 'Frankfurt (TARGET2)', lat: 50.1109, lng: 8.6821, code: 'EUR' },
  { name: 'Dubai (DIFC)', lat: 25.2048, lng: 55.2708, code: 'AED' },
  { name: 'Shanghai (CIPS)', lat: 31.2304, lng: 121.4737, code: 'CNY' },
  { name: 'Sydney (RBA)', lat: -33.8688, lng: 151.2093, code: 'AUD' },
  { name: 'Mumbai (RBI)', lat: 19.076, lng: 72.8777, code: 'INR' },
  { name: 'Sao Paulo (PIX)', lat: -23.5505, lng: -46.6333, code: 'BRL' },
  { name: 'Toronto (Lynx)', lat: 43.6532, lng: -79.3832, code: 'CAD' },
  { name: 'Curacao (Offshore)', lat: 12.1696, lng: -68.9900, code: 'CW' },
  { name: 'Anjouan (Banking)', lat: -12.2128, lng: 44.4374, code: 'KM' },
];

const HIGH_RISK_JURISDICTIONS = [
  { name: 'Curaçao Hub', lat: 12.1696, lng: -68.9900, risk: 94 },
  { name: 'Anjouan Zone', lat: -12.2128, lng: 44.4374, risk: 98 },
  { name: 'Cyprus Offshore', lat: 35.2, lng: 33.4, risk: 88 },
  { name: 'Tehran Direct', lat: 32.4, lng: 53.7, risk: 91 },
  { name: 'Pyongyang Proxy', lat: 40.3, lng: 127.5, risk: 99 },
];

// Create a high-quality fallback canvas texture for realistic Earth rendering
function createProceduralEarthTexture() {
  const canvas = document.createElement('canvas');
  canvas.width = 2048;
  canvas.height = 1024;
  const ctx = canvas.getContext('2d');

  // Deep ocean gradient
  const oceanGrad = ctx.createLinearGradient(0, 0, 0, 1024);
  oceanGrad.addColorStop(0, '#061122');
  oceanGrad.addColorStop(0.5, '#0a1d36');
  oceanGrad.addColorStop(1, '#061122');
  ctx.fillStyle = oceanGrad;
  ctx.fillRect(0, 0, 2048, 1024);

  // Grid lines
  ctx.strokeStyle = 'rgba(0, 240, 255, 0.08)';
  ctx.lineWidth = 1;
  for (let x = 0; x <= 2048; x += 128) {
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, 1024);
    ctx.stroke();
  }
  for (let y = 0; y <= 1024; y += 128) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(2048, y);
    ctx.stroke();
  }

  // Draw continent outlines
  ctx.fillStyle = 'rgba(12, 45, 72, 0.9)';
  ctx.strokeStyle = '#00f0ff';
  ctx.lineWidth = 1.5;

  const toX = (lng) => ((lng + 180) / 360) * 2048;
  const toY = (lat) => ((90 - lat) / 180) * 1024;

  const drawPolygon = (coords) => {
    ctx.beginPath();
    coords.forEach(([lat, lng], i) => {
      const x = toX(lng);
      const y = toY(lat);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.closePath();
    ctx.fill();
    ctx.stroke();
  };

  // Simplified continent polygons for instant fallback
  drawPolygon([[70, -165], [60, -140], [50, -125], [30, -115], [20, -105], [15, -90], [25, -80], [45, -65], [60, -60], [70, -100]]); // N. America
  drawPolygon([[10, -75], [-10, -80], [-35, -72], [-55, -68], [-20, -40], [0, -50], [10, -60]]); // S. America
  drawPolygon([[60, -10], [50, 0], [40, 10], [36, -5], [44, -9], [58, -6]]); // W. Europe
  drawPolygon([[35, -5], [30, 30], [10, 45], [-35, 20], [-30, 15], [5, 10], [15, -17]]); // Africa
  drawPolygon([[70, 40], [60, 100], [50, 140], [35, 120], [20, 80], [30, 50], [50, 40]]); // Eurasia
  drawPolygon([[-12, 130], [-25, 115], [-35, 135], [-38, 145], [-15, 140]]); // Australia

  const texture = new THREE.CanvasTexture(canvas);
  return texture;
}

function RealEarthSphere() {
  const earthRef = useRef();
  const cloudsRef = useRef();
  const [earthTexture, setEarthTexture] = useState(null);

  useEffect(() => {
    // Try to load NASA high-res Earth texture, fall back to procedural
    const loader = new THREE.TextureLoader();
    const fallback = createProceduralEarthTexture();
    setEarthTexture(fallback);

    loader.load(
      'https://unpkg.com/three-globe@2.24.13/example/img/earth-blue-marble.jpg',
      (loadedTex) => {
        setEarthTexture(loadedTex);
      },
      undefined,
      () => {
        // Fallback already set
      }
    );
  }, []);

  useFrame((_, delta) => {
    if (earthRef.current) {
      earthRef.current.rotation.y += delta * 0.05;
    }
    if (cloudsRef.current) {
      cloudsRef.current.rotation.y += delta * 0.07;
    }
  });

  return (
    <group>
      {/* Real Earth Sphere */}
      <mesh ref={earthRef}>
        <sphereGeometry args={[2, 64, 64]} />
        {earthTexture ? (
          <meshStandardMaterial
            map={earthTexture}
            roughness={0.6}
            metalness={0.1}
          />
        ) : (
          <meshPhongMaterial color="#0b1e36" />
        )}
      </mesh>

      {/* Atmospheric Glow */}
      <mesh>
        <sphereGeometry args={[2.04, 64, 64]} />
        <meshBasicMaterial
          color="#00f0ff"
          transparent
          opacity={0.12}
          side={THREE.BackSide}
        />
      </mesh>

      {/* Outer Wireframe Aura */}
      <mesh ref={cloudsRef}>
        <sphereGeometry args={[2.02, 32, 32]} />
        <meshBasicMaterial
          color="#00ff88"
          wireframe
          transparent
          opacity={0.08}
        />
      </mesh>
    </group>
  );
}

function AnimatedArcs({ globeData }) {
  const groupRef = useRef();

  const arcsData = useMemo(() => {
    if (!globeData || globeData.length === 0) {
      // Default demo arcs if live stream empty
      return [
        { start: FINANCIAL_HUBS[0], end: FINANCIAL_HUBS[1], color: '#00ffff' },
        { start: FINANCIAL_HUBS[1], end: FINANCIAL_HUBS[3], color: '#00ff88' },
        { start: FINANCIAL_HUBS[3], end: FINANCIAL_HUBS[4], color: '#ffaa00' },
        { start: FINANCIAL_HUBS[0], end: HIGH_RISK_JURISDICTIONS[0], color: '#ff0055' },
        { start: FINANCIAL_HUBS[2], end: HIGH_RISK_JURISDICTIONS[1], color: '#ff0055' },
      ];
    }

    return globeData.slice(0, 12).map((item, i) => {
      const startHub = FINANCIAL_HUBS[i % FINANCIAL_HUBS.length];
      const endHub = FINANCIAL_HUBS[(i + 3) % FINANCIAL_HUBS.length];
      const isRisk = item.riskScore > 70 || item.risk > 70;
      return {
        start: { lat: item.originLat || startHub.lat, lng: item.originLng || startHub.lng },
        end: { lat: item.destLat || endHub.lat, lng: item.destLng || endHub.lng },
        color: isRisk ? '#ff0055' : '#00ffff',
      };
    });
  }, [globeData]);

  const geometries = useMemo(() => {
    return arcsData.map((arc) => {
      const p1 = latLngToVector3(arc.start.lat, arc.start.lng, 2.01);
      const p2 = latLngToVector3(arc.end.lat, arc.end.lng, 2.01);
      const mid = new THREE.Vector3().addVectors(p1, p2).multiplyScalar(0.5);
      const dist = p1.distanceTo(p2);
      mid.normalize().multiplyScalar(2.01 + dist * 0.25);

      const curve = new THREE.QuadraticBezierCurve3(p1, mid, p2);
      const points = curve.getPoints(40);
      const geometry = new THREE.BufferGeometry().setFromPoints(points);
      return { geometry, color: arc.color };
    });
  }, [arcsData]);

  useFrame((_, delta) => {
    if (groupRef.current) {
      groupRef.current.rotation.y += delta * 0.05;
    }
  });

  return (
    <group ref={groupRef}>
      {geometries.map((g, idx) => (
        <line key={idx}>
          <primitive object={g.geometry} />
          <lineBasicMaterial color={g.color} transparent opacity={0.65} linewidth={2} />
        </line>
      ))}
    </group>
  );
}

function HubPins() {
  const groupRef = useRef();

  useFrame((_, delta) => {
    if (groupRef.current) {
      groupRef.current.rotation.y += delta * 0.05;
    }
  });

  return (
    <group ref={groupRef}>
      {FINANCIAL_HUBS.map((hub) => {
        const pos = latLngToVector3(hub.lat, hub.lng, 2.02);
        return (
          <group key={hub.name} position={pos}>
            <mesh>
              <sphereGeometry args={[0.035, 12, 12]} />
              <meshBasicMaterial color="#00ff88" />
            </mesh>
            <Html distanceFactor={10} position={[0, 0.08, 0]} style={{ pointerEvents: 'none' }}>
              <div style={{
                fontSize: '9px',
                fontFamily: 'monospace',
                color: '#00ff88',
                background: 'rgba(5, 15, 25, 0.85)',
                padding: '2px 5px',
                borderRadius: '3px',
                border: '1px solid rgba(0, 255, 136, 0.4)',
                whiteSpace: 'nowrap',
                fontWeight: 'bold',
              }}>
                {hub.name}
              </div>
            </Html>
          </group>
        );
      })}

      {HIGH_RISK_JURISDICTIONS.map((risk) => {
        const pos = latLngToVector3(risk.lat, risk.lng, 2.02);
        return (
          <group key={risk.name} position={pos}>
            <mesh>
              <sphereGeometry args={[0.05, 12, 12]} />
              <meshBasicMaterial color="#ff0055" />
            </mesh>
            <Html distanceFactor={10} position={[0, 0.08, 0]} style={{ pointerEvents: 'none' }}>
              <div style={{
                fontSize: '9px',
                fontFamily: 'monospace',
                color: '#ff0055',
                background: 'rgba(25, 5, 10, 0.85)',
                padding: '2px 5px',
                borderRadius: '3px',
                border: '1px solid rgba(255, 0, 85, 0.5)',
                whiteSpace: 'nowrap',
                fontWeight: 'bold',
              }}>
                ⚠️ {risk.name} ({risk.risk}%)
              </div>
            </Html>
          </group>
        );
      })}
    </group>
  );
}

export default function Globe3D({ globeData = [] }) {
  return (
    <div style={{ width: '100%', height: '100%', background: '#030814', position: 'relative', overflow: 'hidden' }}>
      <Canvas camera={{ position: [0, 0, 5.8], fov: 45 }}>
        <ambientLight intensity={0.6} />
        <directionalLight position={[10, 10, 10]} intensity={1.2} />
        <pointLight position={[-10, -10, -10]} intensity={0.5} color="#00ffff" />

        <RealEarthSphere />
        <AnimatedArcs globeData={globeData} />
        <HubPins />

        <OrbitControls
          enableZoom={true}
          minDistance={3.5}
          maxDistance={10}
          enableRotate={true}
          rotateSpeed={0.5}
          autoRotate={false}
        />
      </Canvas>

      <div style={{
        position: 'absolute',
        top: 14,
        left: 16,
        color: '#00f0ff',
        fontFamily: "'JetBrains Mono', 'Courier New', monospace",
        fontSize: '11px',
        fontWeight: 'bold',
        letterSpacing: '1px',
        background: 'rgba(3, 10, 20, 0.75)',
        padding: '4px 10px',
        borderRadius: '4px',
        border: '1px solid rgba(0, 240, 255, 0.3)',
      }}>
        🌍 REAL-TIME EARTH MEMPOOL MONITOR
      </div>

      <div style={{
        position: 'absolute',
        bottom: 14,
        right: 16,
        color: '#00ff88',
        fontFamily: "'JetBrains Mono', 'Courier New', monospace",
        fontSize: '10px',
        background: 'rgba(3, 10, 20, 0.75)',
        padding: '4px 10px',
        borderRadius: '4px',
        border: '1px solid rgba(0, 255, 136, 0.3)',
      }}>
        ● 17 Financial Hubs Active · 5 Risk Zones
      </div>
    </div>
  );
}

