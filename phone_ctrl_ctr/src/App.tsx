import { useEffect, useRef, useState } from 'react'
import './App.css'
import './index.css'
import { remote, useRemote } from './remote'
import type { RemoteWindow } from './remote'
import Trackpad from './Trackpad'
import Voice from './Voice'
import Commands from './Commands'

const modes = ['App', 'Trackpad', 'Window', 'Voice', 'Commands'] as const;
const apps = [
  { id: 'chrome', name: 'Chrome' }, { id: 'vscode', name: 'VS Code' },
  { id: 'chatgpt', name: 'ChatGPT' }, { id: 'spotify', name: 'Spotify' },
  { id: 'explorer', name: 'Files' }, { id: 'cmd', name: 'Command Prompt' },
];

type CornerPosition = "top-left" | "top-right";

interface CornerTicksProps {
  position: CornerPosition;
  radius?: number;
  ticks?: number;
  minLength?: number;
  maxLength?: number;
  initialValue?: number | null;
  setting?: 'volume' | 'brightness';
}

interface CornerConfig {
  className: string;
  startAngle: number;
  endAngle: number;
  label: string;
}

const configs: Record<CornerPosition, CornerConfig> = {
  "top-right": {
    className: "top-0 right-0",
    startAngle: -90,
    endAngle: 0,
    label: "Screen brightness",
  },

  "top-left": {
    className: "top-0 left-0",
    startAngle: 180,
    endAngle: 270,
    label: "Speaker volume",
  },
};

export function CornerTicks({
  position,
  radius = 64,
  ticks = 25,
  minLength = 6,
  maxLength = 20,
  initialValue,
  setting,
}: CornerTicksProps) {
  const config = configs[position];
  const [expanded, setExpanded] = useState(false);
  const [value, setLocalValue] = useState(initialValue ?? 0);
  const valueRef = useRef(value);
  const lastChange = useRef(-Infinity);
  const setValue = (next: number | ((current: number) => number)) => {
    if (setting && initialValue === null) return;
    const updated = typeof next === 'function' ? next(valueRef.current) : next;
    valueRef.current = updated; lastChange.current = performance.now(); setLocalValue(updated);
    if (setting) remote.setting(setting, updated);
  };
  useEffect(() => {
    const frame = requestAnimationFrame(() => {
      if (initialValue != null && performance.now() - lastChange.current > 1200) {
        valueRef.current = initialValue; setLocalValue(initialValue);
      }
    });
    return () => cancelAnimationFrame(frame);
  }, [initialValue]);
  const [displayValue, setDisplayValue] = useState(0);
  const animatedValue = useRef(0);
  useEffect(() => {
    let frame: number;
    let previous = performance.now();
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const animate = (now: number) => {
      const amount = reducedMotion ? 1 : 1 - Math.exp(-(now - previous) / 65);
      previous = now;
      animatedValue.current += (value - animatedValue.current) * amount;
      if (Math.abs(value - animatedValue.current) < .005) animatedValue.current = value;
      setDisplayValue(animatedValue.current);
      if (animatedValue.current !== value) frame = requestAnimationFrame(animate);
    };
    frame = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(frame);
  }, [value]);
  const drag = useRef<{ startY: number; startValue: number; moved: boolean } | null>(null);
  const wheelDistance = useRef(0);
  const clamp = (next: number) => Math.max(0, Math.min(100, next));
  const inwardDirection = position.startsWith('top') ? 1 : -1;
  const extension = radius * 0.8;
  const arcLength = radius * Math.PI / 2;
  const pathLength = extension * 2 + arcLength;
  const spacing = pathLength / (ticks - 1);
  const movingTicks = ticks * 2 - 1;

  return (
    <div
      className={`fixed ${config.className} z-50 corner-control corner-${position}`}
      style={{
        width: radius * 2,
        height: radius * 2,
      }}
      role="slider"
      tabIndex={0}
      aria-label={config.label}
      aria-disabled={Boolean(setting && initialValue === null)}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(value)}
      aria-valuetext={`${Math.round(value)}%`}
      onPointerDown={event => {
        drag.current = { startY: event.clientY, startValue: value, moved: false };
        event.currentTarget.setPointerCapture(event.pointerId);
      }}
      onPointerMove={event => {
        if (!drag.current) return;
        const distance = (event.clientY - drag.current.startY) * inwardDirection;
        if (!drag.current.moved && Math.abs(distance) < 10) return;
        drag.current.moved = true;
        setExpanded(true);
        const travel = Math.sign(distance) * Math.max(0, Math.abs(distance) - 10);
        setValue(clamp(drag.current.startValue + travel / 1.4));
      }}
      onPointerUp={() => {
        if (drag.current && !drag.current.moved) setExpanded(current => !current);
        drag.current = null;
      }}
      onPointerCancel={() => { drag.current = null; }}
      onWheel={event => {
        wheelDistance.current += event.deltaY;
        const steps = Math.trunc(wheelDistance.current / 24);
        if (steps === 0) return;
        wheelDistance.current -= steps * 24;
        setExpanded(true);
        setValue(current => clamp(current + steps * 5));
      }}
      onKeyDown={event => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          setExpanded(current => !current);
        } else if (event.key === 'ArrowUp' || event.key === 'ArrowRight') {
          event.preventDefault();
          setExpanded(true);
          setValue(current => clamp(current + 5));
        } else if (event.key === 'ArrowDown' || event.key === 'ArrowLeft') {
          event.preventDefault();
          setExpanded(true);
          setValue(current => clamp(current - 5));
        } else if (event.key === 'Home' || event.key === 'End') {
          event.preventDefault();
          setExpanded(true);
          setValue(event.key === 'Home' ? 0 : 100);
        }
      }}
    >
      {Array.from({ length: movingTicks }).map((_, index) => {
        // Scroll the whole sequence across a straight edge, the rounded corner,
        // and the next straight edge. Extra ticks enter as earlier ones leave.
        const distance = index * spacing - (displayValue / 100) * pathLength;
        const edgeOpacity = Math.max(0, Math.min(1, distance / spacing, (pathLength - distance) / spacing));
        const onPath = Math.max(0, Math.min(pathLength, distance));
        const onArc = Math.max(0, Math.min(arcLength, onPath - extension));
        const angle = config.startAngle + onArc / radius * 180 / Math.PI;
        const radians = angle * Math.PI / 180;
        const straightOffset = onPath < extension
          ? onPath - extension
          : onPath > extension + arcLength
            ? onPath - extension - arcLength
            : 0;
        const x = radius + Math.cos(radians) * radius - Math.sin(radians) * straightOffset;
        const y = radius + Math.sin(radians) * radius + Math.cos(radians) * straightOffset;
        const cornerProximity = Math.max(0, 1 - Math.abs(onArc / arcLength - .5) * 2);
        const length = minLength + cornerProximity * (maxLength - minLength);

        return (
          <div
            key={index}
            className="absolute h-px bg-white/60 rounded-full corner-tick"
            style={{
              left: x,
              top: y,
              width: length + (expanded ? 8 : 0),
              height: expanded ? 'calc(1px + 0.125rem)' : '1px',
              opacity: edgeOpacity,
              backgroundColor: expanded ? '#fff' : 'rgba(255,255,255,.6)',
              transformOrigin: "0 50%",
              transform: `translateY(-50%) rotate(${angle + 180}deg)`,
            }}
          />
        );
      })}
      <div className={`corner-readout${expanded ? ' is-visible' : ''}`} aria-hidden={!expanded}>
        <span className="corner-percentage">{setting && initialValue === null ? '—' : `${Math.round(value)}%`}</span>
        <span className="corner-subheader">{config.label}</span>
      </div>
    </div>
  );
}

export default function App() {
  const { state, status } = useRemote();
  const [voiceHandsFree, setVoiceHandsFree] = useState(false);
  useEffect(() => {
    if (status === 'online') return;
    const frame = requestAnimationFrame(() => setVoiceHandsFree(false));
    return () => cancelAnimationFrame(frame);
  }, [status]);
  const [active, setActive] = useState(0);
  const [openMode, setOpenMode] = useState<typeof modes[number] | null>(null);
  const [transitionPhase, setTransitionPhase] = useState<'out' | 'in' | null>(null);
  const nextMode = useRef<typeof modes[number] | null>(null);
  const headings = useRef<(HTMLButtonElement | null)[]>([]);
  const pointerStart = useRef<number | null>(null);
  const lastSwipe = useRef(-Infinity);

  const move = (direction: number) => {
    setActive(current => (current + direction + modes.length) % modes.length);
  };
  const changeMode = (mode: typeof modes[number] | null) => {
    if (transitionPhase) return;
    nextMode.current = mode;
    setTransitionPhase('out');
  };
  const closeMode = () => changeMode(null);

  return (
    <div className="phone-shell relative w-screen bg-black overflow-hidden">

      <CornerTicks position="top-right" initialValue={state?.brightness} setting="brightness" />

      <CornerTicks position="top-left" initialValue={state?.volume} setting="volume" />

      <button type="button" className="media-control" aria-label="Play or pause media" disabled={status !== 'online'}
        onClick={() => remote.send({ type: 'media', action: 'playPause' })}>
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 5 9 7-9 7Z"/><path d="M17 5v14M21 5v14"/></svg>
      </button>

      <div className={`mode-view${transitionPhase ? ` is-${transitionPhase}` : ''}`}
        onAnimationEnd={event => {
          if (event.target !== event.currentTarget) return;
          if (transitionPhase === 'out') {
            setOpenMode(nextMode.current);
            setTransitionPhase('in');
            if (nextMode.current === null) requestAnimationFrame(() => headings.current[active]?.focus());
          } else {
            setTransitionPhase(null);
          }
        }}>
      {openMode === null ? <section
        className="mode-carousel"
        aria-label="Modes"
        tabIndex={0}
        onKeyDown={event => {
          if (event.key === 'ArrowRight') { event.preventDefault(); move(1); }
          if (event.key === 'ArrowLeft') { event.preventDefault(); move(-1); }
        }}
        onPointerDown={event => {
          pointerStart.current = event.clientX;
        }}
        onPointerUp={event => {
          if (pointerStart.current === null) return;
          const distance = event.clientX - pointerStart.current;
          if (Math.abs(distance) > 40) {
            move(distance < 0 ? 1 : -1);
            lastSwipe.current = performance.now();
          }
          pointerStart.current = null;
        }}
        onPointerCancel={() => { pointerStart.current = null; }}
      >
        {modes.map((mode, index) => {
          const offset = (index - active + modes.length) % modes.length;
          const position = offset === 0 ? 'center' : offset === 1 ? 'right' : offset === modes.length - 1 ? 'left' : 'hidden';
          return (
            <button
              key={mode}
              ref={element => { headings.current[index] = element; }}
              type="button"
              className={`mode-heading mode-${position}`}
              aria-current={position === 'center' ? 'true' : undefined}
              aria-hidden={position === 'hidden'}
              tabIndex={position === 'hidden' ? -1 : 0}
              onClick={() => {
                if (performance.now() - lastSwipe.current > 300) {
                  setActive(index);
                  changeMode(mode);
                }
              }}
            >
              {mode}
            </button>
          );
        })}
      </section> : <section className="mode-screen" aria-label={`${openMode} mode`}
        onKeyDown={event => { if (event.key === 'Escape') closeMode(); }}>
        <div className="mode-toolbar">
        <button type="button" className="mode-close" aria-label="Close mode" onClick={closeMode} autoFocus>
          <svg viewBox="0 0 16 16" aria-hidden="true"><path d="m4 4 8 8M12 4l-8 8" /></svg>
        </button>
        </div>
        <div className="mode-content">
        {openMode === 'App' && <div className="app-grid">
          {apps.map(app => <button key={app.id} type="button"
            className="app-placeholder" aria-label={`Open ${app.name}`} disabled={!state?.apps.includes(app.id)}
            onClick={() => remote.send({ type: 'launch', app: app.id })}><span>{app.name}</span></button>)}
        </div>}
        {openMode === 'Trackpad' && <Trackpad />}
        {openMode === 'Voice' && <Voice handsFree={voiceHandsFree} onHandsFree={setVoiceHandsFree} />}
        {openMode === 'Commands' && <Commands />}
        {openMode === 'Window' && <WindowSwitcher />}
        </div>
      </section>}
      </div>

    </div>
  );
}

function WindowSwitcher() {
  const { state } = useRemote();
  const [windows, setWindows] = useState<RemoteWindow[]>(state?.windows || []);
  const [page, setPage] = useState(0);
  const strip = useRef<HTMLDivElement>(null);
  const drag = useRef<{ x: number; scroll: number } | null>(null);
  const settle = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const focused = useRef<string | null>(null);
  const selectedPage = useRef(0);
  const touching = useRef(false);
  const resizing = useRef(false);
  useEffect(() => {
    const element = strip.current;
    if (!element) return;
    let width = element.clientWidth;
    let frame = 0;
    const observer = new ResizeObserver(() => {
      if (element.clientWidth === width) return;
      width = element.clientWidth;
      resizing.current = true; clearTimeout(settle.current);
      element.scrollTo({ left: selectedPage.current * width, behavior: 'instant' });
      setPage(selectedPage.current);
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => { resizing.current = false; });
    });
    observer.observe(element);
    return () => { observer.disconnect(); cancelAnimationFrame(frame); };
  }, []);
  useEffect(() => {
    let mounted = true;
    const refresh = () => remote.request({ type: 'windows' }).then(result => {
      if (!mounted) return;
      const latest = result as RemoteWindow[];
      setWindows(current => [...current.filter(w => latest.some(next => next.id === w.id)).map(w => latest.find(next => next.id === w.id)!), ...latest.filter(w => !current.some(previous => previous.id === w.id))]);
    }).catch(() => {});
    void refresh(); const timer = setInterval(refresh, 6000);
    return () => { mounted = false; clearInterval(timer); clearTimeout(settle.current); };
  }, []);
  const onScroll = (element: HTMLDivElement) => {
    if (resizing.current) return;
    const index = Math.max(0, Math.min(windows.length - 1, Math.round(element.scrollLeft / element.clientWidth)));
    setPage(index); clearTimeout(settle.current);
    settle.current = setTimeout(() => {
      if (touching.current || drag.current) return;
      selectedPage.current = index;
      const selected = windows[index];
      if (selected && focused.current !== selected.id) { focused.current = selected.id; remote.send({ type: 'focus', id: selected.id }); }
    }, 180);
  };
  return <div className="window-switcher">
    {windows.length === 0 && <p className="window-empty">No open windows</p>}
    <div className="window-strip" ref={strip} tabIndex={0} aria-label="Swipe between windows"
      onScroll={event => onScroll(event.currentTarget)}
      onTouchStart={() => { touching.current = true; }}
      onTouchEnd={event => { touching.current = false; onScroll(event.currentTarget); }}
      onTouchCancel={() => { touching.current = false; clearTimeout(settle.current); }}
      onKeyDown={event => {
        if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
        event.preventDefault();
        const next = Math.max(0, Math.min(windows.length - 1, page + (event.key === 'ArrowRight' ? 1 : -1)));
        selectedPage.current = next;
        event.currentTarget.scrollTo({ left: next * event.currentTarget.clientWidth, behavior: 'smooth' });
      }}
      onPointerDown={event => {
        if (event.pointerType !== 'mouse') return;
        drag.current = { x: event.clientX, scroll: event.currentTarget.scrollLeft };
        event.currentTarget.setPointerCapture(event.pointerId);
        event.currentTarget.style.scrollSnapType = 'none';
      }}
      onPointerMove={event => {
        if (drag.current) event.currentTarget.scrollLeft = drag.current.scroll + drag.current.x - event.clientX;
      }}
      onPointerUp={event => {
        if (!drag.current) return;
        const direction = drag.current.x - event.clientX;
        const initial = Math.round(drag.current.scroll / event.currentTarget.clientWidth);
        const next = Math.max(0, Math.min(windows.length - 1, initial + (Math.abs(direction) > 40 ? Math.sign(direction) : 0)));
        selectedPage.current = next;
        drag.current = null;
        event.currentTarget.style.scrollSnapType = '';
        event.currentTarget.scrollTo({ left: next * event.currentTarget.clientWidth, behavior: 'smooth' });
      }}
      onPointerCancel={event => { drag.current = null; event.currentTarget.style.scrollSnapType = ''; }}>
      {windows.map(item => <div className="window-page" key={item.id} aria-label={item.title}>
        <div className="window-placeholder"><div className="window-topline"><span /><span /><span /></div><p className="window-title">{item.title}</p></div>
      </div>)}
    </div>
    <div className="window-pagination">
      {windows.map((item, index) => <button key={item.id} type="button" className={page === index ? 'selected' : ''}
        aria-label={`Show ${item.title}`} aria-current={page === index ? 'true' : undefined}
        onClick={() => { selectedPage.current = index; strip.current?.scrollTo({ left: index * strip.current.clientWidth, behavior: 'smooth' }); }} />)}
    </div>
  </div>;
}
