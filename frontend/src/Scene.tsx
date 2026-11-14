import { Canvas, useFrame, useThree } from "@react-three/fiber";
import {
  ContactShadows,
  OrbitControls,
  PerspectiveCamera,
} from "@react-three/drei";
import { Children, Suspense, useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import type { Sample } from "./types";

function Pipe({
  a,
  b,
  r = 0.075,
  color = "#8a9897",
}: {
  a: [number, number, number];
  b: [number, number, number];
  r?: number;
  color?: string;
}) {
  const start = useMemo(() => new THREE.Vector3(...a), [...a]);
  const end = useMemo(() => new THREE.Vector3(...b), [...b]);
  const delta = end.clone().sub(start);
  const mid = start.clone().add(end).multiplyScalar(0.5);
  const q = new THREE.Quaternion().setFromUnitVectors(
    new THREE.Vector3(0, 1, 0),
    delta.clone().normalize(),
  );
  return (
    <mesh position={mid} quaternion={q} castShadow>
      <cylinderGeometry args={[r, r, delta.length(), 16]} />
      <meshStandardMaterial color={color} metalness={0.7} roughness={0.3} />
    </mesh>
  );
}
function Label({
  position,
  children,
}: {
  position: [number, number, number];
  children: React.ReactNode;
}) {
  const text = Children.toArray(children).join("");
  const { texture, width } = useMemo(() => {
    const canvas = document.createElement("canvas");
    const context = canvas.getContext("2d")!;
    context.font = "600 24px sans-serif";
    const width = Math.ceil(context.measureText(text).width) + 32;
    canvas.width = width;
    canvas.height = 48;
    context.fillStyle = "#f9faf4";
    context.fillRect(0, 0, width, 48);
    context.strokeStyle = "#cfd9cb";
    context.strokeRect(0.5, 0.5, width - 1, 47);
    context.fillStyle = "#527164";
    context.font = "600 24px sans-serif";
    context.fillText(text, 16, 32);
    const texture = new THREE.CanvasTexture(canvas);
    texture.colorSpace = THREE.SRGBColorSpace;
    return { texture, width };
  }, [text]);
  useEffect(() => () => texture.dispose(), [texture]);
  return (
    <sprite position={position} scale={[width / 240, 0.2, 1]}>
      <spriteMaterial map={texture} transparent depthTest={false} />
    </sprite>
  );
}
function along(
  points: [number, number, number][],
  progress: number,
): [number, number, number] {
  const scaled = progress * (points.length - 1),
    i = Math.min(Math.floor(scaled), points.length - 2),
    f = scaled - i;
  return points[i].map((v, j) => v + (points[i + 1][j] - v) * f) as [
    number,
    number,
    number,
  ];
}
function CameraActions({
  selected,
  focusKey,
  resetKey,
}: {
  selected: string;
  focusKey: number;
  resetKey: number;
}) {
  const { camera, controls } = useThree();
  const mounted = useRef(false);
  const destination = useRef<{
    position: THREE.Vector3;
    target: THREE.Vector3;
  } | null>(null);
  useEffect(() => {
    if (!mounted.current) {
      mounted.current = true;
      return;
    }
    const positions: Record<string, [number, number, number]> = {
      exchanger: [0, 0, 0],
      valve: [-2.65, -0.4, 0],
      source: [-3.65, -0.4, 0],
      pump: [2.48, -1.35, 0],
      sensor: [1.1, -0.65, 0],
    };
    const target = new THREE.Vector3(...positions[selected]);
    destination.current = {
      target,
      position: target.clone().add(new THREE.Vector3(3, 2, 4)),
    };
  }, [focusKey]);
  useEffect(() => {
    destination.current = {
      target: new THREE.Vector3(0, 0.1, 0),
      position: new THREE.Vector3(6, 4.3, 8),
    };
  }, [resetKey]);
  useFrame((_, delta) => {
    const goal = destination.current;
    if (!goal) return;
    const alpha = 1 - Math.exp(-5 * delta);
    camera.position.lerp(goal.position, alpha);
    const orbit = controls as unknown as {
      target: THREE.Vector3;
      update: () => void;
    } | null;
    if (orbit) {
      orbit.target.lerp(goal.target, alpha);
      orbit.update();
    }
    if (
      camera.position.distanceTo(goal.position) < 0.01 &&
      (!orbit || orbit.target.distanceTo(goal.target) < 0.01)
    )
      destination.current = null;
  });
  return null;
}
function Exchanger({
  sample,
  time,
  cutaway,
  exploded,
  selected,
  onSelect,
}: {
  sample: Sample;
  time: number;
  cutaway: boolean;
  exploded: boolean;
  selected: string;
  onSelect: (s: string) => void;
}) {
  const hot = new THREE.Color("#d16a3e").lerp(
    new THREE.Color("#ffba72"),
    THREE.MathUtils.clamp((sample.th - 40) / 45, 0, 1),
  );
  const cold = new THREE.Color("#3a8988").lerp(
    new THREE.Color("#8ad4b5"),
    THREE.MathUtils.clamp((sample.tc - 25) / 45, 0, 1),
  );
  const tubeCoords = [
    [0, 0],
    [0.25, 0],
    [-0.25, 0],
    [0, 0.25],
    [0, -0.25],
    [0.18, 0.18],
    [-0.18, -0.18],
    [0.18, -0.18],
    [-0.18, 0.18],
  ];
  return (
    <group position={[0, 0.2, 0]}>
      <mesh
        position={[0, 0, 0]}
        rotation={[0, 0, Math.PI / 2]}
        onClick={() => onSelect("exchanger")}
        castShadow
      >
        <cylinderGeometry
          args={[
            0.69,
            0.69,
            3.3,
            40,
            1,
            cutaway,
            cutaway ? 0 : 0,
            cutaway ? Math.PI * 1.45 : Math.PI * 2,
          ]}
        />
        <meshPhysicalMaterial
          color="#a6b1a9"
          metalness={0.7}
          roughness={0.28}
          transparent={cutaway}
          opacity={cutaway ? 0.26 : 1}
          side={THREE.DoubleSide}
        />
      </mesh>
      {[-1.72, 1.72].map((x) => (
        <group
          key={x}
          position={[x + (exploded ? Math.sign(x) * 0.42 : 0), 0, 0]}
        >
          <mesh rotation={[0, 0, Math.PI / 2]} castShadow>
            <cylinderGeometry args={[0.74, 0.74, 0.16, 36]} />
            <meshStandardMaterial
              color="#62716e"
              metalness={0.75}
              roughness={0.3}
            />
          </mesh>
          <mesh
            position={[Math.sign(x) * 0.11, 0, 0]}
            rotation={[0, 0, Math.PI / 2]}
          >
            <cylinderGeometry args={[0.6, 0.68, 0.12, 36]} />
            <meshStandardMaterial
              color="#b4beb4"
              metalness={0.7}
              roughness={0.3}
            />
          </mesh>
        </group>
      ))}
      {(cutaway || exploded) &&
        tubeCoords.map(([y, z], i) => (
          <mesh key={i} position={[0, y, z]} rotation={[0, 0, Math.PI / 2]}>
            <cylinderGeometry args={[0.045, 0.045, 3.45, 12]} />
            <meshStandardMaterial
              color={i % 2 ? hot : "#c5a66f"}
              metalness={0.65}
              roughness={0.27}
            />
          </mesh>
        ))}
      {(cutaway || exploded) &&
        [-0.9, 0, 0.9].map((x) => (
          <mesh key={x} position={[x, 0, 0]} rotation={[0, Math.PI / 2, 0]}>
            <ringGeometry args={[0.52, 0.61, 32]} />
            <meshStandardMaterial
              color="#b8c8bb"
              metalness={0.8}
              side={THREE.DoubleSide}
            />
          </mesh>
        ))}
      <Pipe a={[-3.5, -0.4, 0]} b={[-1.78, -0.4, 0]} color="#b46d4d" />
      <Pipe a={[1.78, 0.4, 0]} b={[3.25, 0.4, 0]} color="#b46d4d" />
      <Pipe a={[-0.95, 1.45, 0]} b={[-0.95, 0.62, 0]} color="#629b9b" />
      <Pipe a={[-0.95, 1.45, 0]} b={[-3.2, 1.45, 0]} color="#629b9b" />
      <Pipe a={[0.95, -0.62, 0]} b={[0.95, -1.35, 0]} color="#629b9b" />
      <Pipe a={[0.95, -1.35, 0]} b={[3.1, -1.35, 0]} color="#629b9b" />
      <mesh position={[-2.65, -0.4, 0]} onClick={() => onSelect("valve")}>
        <octahedronGeometry args={[0.21, 0]} />
        <meshStandardMaterial
          color="#dca15e"
          metalness={0.65}
          roughness={0.3}
        />
      </mesh>
      <mesh
        position={[-2.65, -0.08, 0]}
        rotation={[0, 0, (sample.valve * Math.PI) / 2]}
      >
        <boxGeometry args={[0.5, 0.045, 0.08]} />
        <meshStandardMaterial color="#d6a05d" />
      </mesh>
      <mesh
        position={[-3.65, -0.4, 0]}
        onClick={() => onSelect("source")}
        castShadow
      >
        <cylinderGeometry args={[0.38, 0.38, 0.8, 24]} />
        <meshStandardMaterial
          color="#c9c5ad"
          metalness={0.65}
          roughness={0.35}
        />
      </mesh>
      <mesh
        position={[2.48, -1.35, 0]}
        rotation={[0, 0, Math.PI / 2]}
        onClick={() => onSelect("pump")}
      >
        <cylinderGeometry args={[0.21, 0.21, 0.35, 24]} />
        <meshStandardMaterial color="#819a91" metalness={0.7} roughness={0.3} />
      </mesh>
      {Array.from({ length: 9 }, (_, i) => {
        const p = (time * (0.009 + sample.hot_flow * 0.18) + i / 9) % 1;
        return (
          <mesh
            key={"h" + i}
            position={along(
              [
                [-3.35, -0.4, 0.12],
                [-1.78, -0.4, 0.12],
                [-1.6, 0, 0.12],
                [1.6, 0, 0.12],
                [1.78, 0.4, 0.12],
                [3.2, 0.4, 0.12],
              ],
              p,
            )}
          >
            <sphereGeometry args={[0.047, 8, 8]} />
            <meshBasicMaterial color={hot} />
          </mesh>
        );
      })}
      {Array.from({ length: 8 }, (_, i) => {
        const p = (time * (0.008 + sample.mc * 0.15) + i / 8) % 1;
        return (
          <mesh
            key={"c" + i}
            position={along(
              [
                [-3.05, 1.45, 0.12],
                [-0.95, 1.45, 0.12],
                [-0.95, 0.62, 0.12],
                [-0.6, 0.35, 0.35],
                [0, 0, 0.42],
                [0.6, -0.35, 0.35],
                [0.95, -0.62, 0.12],
                [0.95, -1.35, 0.12],
                [3.05, -1.35, 0.12],
              ],
              p,
            )}
          >
            <sphereGeometry args={[0.04, 8, 8]} />
            <meshBasicMaterial color={cold} />
          </mesh>
        );
      })}
      <mesh position={[1.1, -0.65, 0.12]} onClick={() => onSelect("sensor")}>
        <sphereGeometry args={[0.11, 16, 16]} />
        <meshStandardMaterial
          color="#8dc1a8"
          emissive="#547965"
          emissiveIntensity={0.3}
        />
      </mesh>
      <Label position={[1.25, -0.9, 0.2]}>
        TT-102 · {sample.measurement.toFixed(1)} °C
      </Label>
      {[
        [-2.05, -0.4, 0.2],
        [2.3, 0.4, 0.2],
        [-2.1, 1.45, 0.2],
        [2.1, -1.35, 0.2],
      ].map((p, i) => (
        <mesh
          key={i}
          position={p as [number, number, number]}
          rotation={[0, 0, -Math.PI / 2]}
        >
          <coneGeometry args={[0.09, 0.2, 12]} />
          <meshBasicMaterial color={i < 2 ? "#ecaa76" : "#75bbb4"} />
        </mesh>
      ))}
      <Label position={[2.6, 0.75, 0]}>
        HOT OUT · {sample.th.toFixed(1)} °C
      </Label>
      <Label position={[-0.05, 0.95, 0]}>HX-101 · SHELL & TUBE</Label>
      <Label position={[-3.65, 0.3, 0]}>HEAT SOURCE*</Label>
      <Label position={[-2.65, 0.4, 0]}>
        TV-101 · {(sample.valve * 100).toFixed(0)}%
      </Label>
      <Label position={[2.55, -1.8, 0]}>COLD SIDE PUMP</Label>
      {selected === "exchanger" && (
        <Label position={[0.1, -0.9, 0]}>
          Q {(sample.heat_w / 1000).toFixed(2)} kW
        </Label>
      )}
    </group>
  );
}
export default function Scene({
  sample,
  time,
  cutaway,
  exploded,
  selected,
  onSelect,
  resetKey,
  focusKey,
}: {
  sample: Sample;
  time: number;
  cutaway: boolean;
  exploded: boolean;
  selected: string;
  onSelect: (s: string) => void;
  resetKey: number;
  focusKey: number;
}) {
  const supported = useMemo(() => {
    try {
      const canvas = document.createElement("canvas");
      const gl = canvas.getContext("webgl2") || canvas.getContext("webgl");
      if (gl) gl.getExtension("WEBGL_lose_context")?.loseContext();
      return !!gl;
    } catch {
      return false;
    }
  }, []);
  if (!supported)
    return (
      <div className="webgl-fallback">
        WebGL is unavailable. The simulation readings and charts remain
        available.
      </div>
    );
  return (
    <Canvas
      shadows
      dpr={[1, 1.5]}
      gl={{ antialias: true }}
      fallback={
        <div className="webgl-fallback">
          WebGL is unavailable. The live data and charts remain available.
        </div>
      }
    >
      <color attach="background" args={["#e7eae0"]} />
      <fog attach="fog" args={["#e7eae0", 12, 25]} />
      <PerspectiveCamera makeDefault position={[6, 4.3, 8]} fov={37} />
      <ambientLight intensity={1.25} />
      <directionalLight
        position={[4, 8, 5]}
        intensity={2.1}
        castShadow
        shadow-mapSize={[1024, 1024]}
      />
      <Suspense fallback={null}>
        <Exchanger
          sample={sample}
          time={time}
          cutaway={cutaway}
          exploded={exploded}
          selected={selected}
          onSelect={onSelect}
        />
        <ContactShadows
          position={[0, -1.5, 0]}
          opacity={0.2}
          scale={15}
          blur={2.7}
        />
      </Suspense>
      <gridHelper
        args={[20, 40, "#bcc8ba", "#d4ddd0"]}
        position={[0, -1.52, 0]}
      />
      <OrbitControls
        makeDefault
        enablePan
        minDistance={3}
        maxDistance={16}
        target={[0, 0.1, 0]}
      />
      <CameraActions
        selected={selected}
        focusKey={focusKey}
        resetKey={resetKey}
      />
    </Canvas>
  );
}
