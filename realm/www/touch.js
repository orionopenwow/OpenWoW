// ow/touch.js — Open Vanilla's touch controls for phones and tablets (docs: the Mobile Controls Plan).
//
// Loaded by ow/openvanilla.js on every play page; it only switches on for a touch screen (a coarse
// pointer and touch points), or with ?touch=1 (?touch=0 turns it off, remembered as "ow:touch").
// Everything goes through the page bridge (window.wenilla), so the game sees exactly what keys
// and a mouse would do:
//
//   * Floating stick, bottom-left (24 px in, 120 px range): holds MOVEFORWARD / MOVEBACKWARD / STRAFELEFT / STRAFERIGHT; a double-tap toggles auto-run.
//   * Right-thumb cluster, pivoting on the bottom-right corner: a 72 px Attack/Interact key showing
//     what a tap does with the target in the game's own art (the hover sword for an enemy, loot
//     bags, speech bubble, anvil hammer, trainer's book, flight boot, the quest "!" and "?" from the
//     Quests addon's data); the target reticle above it (hold: clear target); an arc of four 48 px
//     ability keys with the real icons, cooldowns, range and mana; empty slots as dark sockets.
//     Swipe a key sideways, or tap the dots, for the next four actions. Hold a key for its tooltip,
//     with Move and Remove; anything dragged out of the Spellbook or bags lands on the next key tapped.
//   * Jump pill under Attack: JUMP.
//   * One tray button in the top-right corner slides Bags, Quests, Chat and Menu (a big-icon sheet)
//     out along the top edge and folds them away again, so nothing sits next to the cluster during a fight.
//   * Close (top centre) whenever a window is open; windows over the stick take the touch.
//   * Stances / forms and the pet bar as a short row along the bottom edge (hold a pet action:
//     autocast). Auto loot (setting). Whispers and party chat light the tray and pop up.
//   * Typing: a text bar appears when one of the game's text boxes has focus (mail, auction search,
//     names...); a keyboard button on the character screens relays keys to the glue screens.
//   * Menu > Controls: Classic (stick strafes, drag turns you), Simple (stick turns, drag only
//     looks, the camera follows), Keyboard & mouse (touch off, a corner button to come back), with
//     a phone-vs-PC table. Interface size and auto loot sit next to it.
//   * The rest of the screen: tap = click (target, buttons, windows), double-tap = right-click
//     (talk, loot, open), long-press = hover (tooltips), drag = turn the camera (or drag a window),
//     two-finger pinch = zoom.
//   * In the world the game's own frames are rearranged for a small screen (bigger interface;
//     player and target frames side by side along the top-left edge, the quest arrow top-centre,
//     minimap top-right, tutorial alerts above the bottom edge, action bars and chat hidden:
//     the cluster and the chat sheet replace them); all restored when touch is turned off.
//   * Phones: every game screen asks to be turned sideways in portrait (the glue screens are laid
//     out for landscape), and sideways but not full screen one tap goes full screen and locks
//     landscape (browsers only allow it from a tap; iPhone Safari can't, so it suggests Add to
//     Home Screen, whose manifest opens full screen in landscape). Login, realm, character list
//     and creation all take taps; a tap during a resize or rotation is dropped, not misplaced.
//   * A gamepad connecting hands over to the bridge's gamepad mapper and hides the touch controls.
//
// The art is drawn here as vector graphics (crisp at any screen density), in the look of the
// Open Vanilla mobile mockups: dark stone faces and bronze-gold rims.
// Never load-bearing: any failure leaves the game as it was. window.owTouch for owdiag.

// Shown on the ?touchdebug=1 line, so a phone can tell at a glance which build it is running.
import { gamePointerEvent } from './input.js';

export const TOUCH_BUILD = '2026-10-24 game-tick taps';

const LS = (k, v) => {
  try {
    if (v === undefined) return localStorage.getItem(k);
    if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v);
  } catch { /* storage blocked */ }
  return null;
};

// -- When it is on ------------------------------------------------------------------------------

export function wanted() {
  const q = new URLSearchParams(location.search).get('touch');
  if (q === '1' || q === 'on') LS('ow:touch', 'on');
  else if (q === '0' || q === 'off') LS('ow:touch', 'off');
  const pref = LS('ow:touch');
  if (pref === 'on') return true;
  if (pref === 'off') return false;
  return matchMedia('(pointer: coarse)').matches && (navigator.maxTouchPoints || 0) > 0;
}

// -- Art (SVG) ----------------------------------------------------------------------------------

const GOLD = `<linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#f6dc93"/><stop offset=".45" stop-color="#c79a3c"/><stop offset=".75" stop-color="#8a6122"/><stop offset="1" stop-color="#e2bd6a"/></linearGradient>`;
const svgUrl = (s) => `url("data:image/svg+xml;charset=utf-8,${encodeURIComponent(s)}")`;

export const ART = {
  stickBase: svgUrl(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120"><defs>${GOLD}<radialGradient id="f" cx=".5" cy=".42" r=".6"><stop offset="0" stop-color="#2a2733" stop-opacity=".62"/><stop offset="1" stop-color="#07060b" stop-opacity=".78"/></radialGradient></defs><circle cx="60" cy="60" r="57" fill="url(#f)" stroke="url(#g)" stroke-width="3"/><circle cx="60" cy="60" r="52" fill="none" stroke="#000" stroke-opacity=".45" stroke-width="2"/><circle cx="60" cy="60" r="36" fill="none" stroke="#e8c879" stroke-opacity=".22" stroke-width="1.5"/><g fill="#f0d79a" fill-opacity=".8"><path d="M60 9l8 10h-16z"/><path d="M60 111l8-10h-16z"/><path d="M9 60l10-8v16z"/><path d="M111 60l-10-8v16z"/></g><g fill="#f0d79a" fill-opacity=".38"><path d="M24 24l10 2-8 8z"/><path d="M96 24l-2 10-8-8z"/><path d="M24 96l2-10 8 8z"/><path d="M96 96l-10-2 8-8z"/></g></svg>`),
  knob: svgUrl(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 52 52"><defs>${GOLD}<radialGradient id="k" cx=".4" cy=".32" r=".75"><stop offset="0" stop-color="#7d7884"/><stop offset=".55" stop-color="#3a3641"/><stop offset="1" stop-color="#141218"/></radialGradient></defs><circle cx="26" cy="26" r="24" fill="url(#k)" stroke="url(#g)" stroke-width="2.6"/><ellipse cx="21" cy="17" rx="10" ry="5" fill="#fff" fill-opacity=".12"/></svg>`),
  ring: svgUrl(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48"><defs>${GOLD}</defs><circle cx="24" cy="24" r="21.6" fill="none" stroke="#000" stroke-opacity=".55" stroke-width="2"/><circle cx="24" cy="24" r="22" fill="none" stroke="url(#g)" stroke-width="3.2"/><circle cx="24" cy="24" r="19.6" fill="none" stroke="#000" stroke-opacity=".6" stroke-width="1.4"/></svg>`),
  emptyFace: svgUrl(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48"><defs><radialGradient id="e" cx=".45" cy=".35" r=".7"><stop offset="0" stop-color="#5d5a62"/><stop offset="1" stop-color="#26242b"/></radialGradient></defs><circle cx="24" cy="24" r="21" fill="url(#e)"/></svg>`),
  attack: svgUrl(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96"><defs>${GOLD}<radialGradient id="a" cx=".5" cy=".42" r=".62"><stop offset="0" stop-color="#4a3a31"/><stop offset=".7" stop-color="#1f1612"/><stop offset="1" stop-color="#0d0908"/></radialGradient><radialGradient id="em" cx=".5" cy="1" r=".6"><stop offset="0" stop-color="#ff7a24" stop-opacity=".28"/><stop offset="1" stop-color="#ff7a24" stop-opacity="0"/></radialGradient><filter id="b" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="2.6"/></filter></defs><circle cx="48" cy="48" r="38" fill="url(#a)"/><circle cx="48" cy="48" r="38" fill="url(#em)"/><circle cx="48" cy="48" r="38" fill="none" stroke="url(#g)" stroke-width="4"/><circle cx="48" cy="48" r="34.5" fill="none" stroke="#000" stroke-opacity=".55" stroke-width="1.5"/><g fill="url(#g)"><path d="M48 3l4 8h-8z"/><path d="M48 93l4-8h-8z"/><path d="M3 48l8-4v8z"/><path d="M93 48l-8-4v8z"/></g></svg>`),
  pill: svgUrl(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 34" preserveAspectRatio="none"><defs>${GOLD}<linearGradient id="p" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#4a4850"/><stop offset=".5" stop-color="#2b2a31"/><stop offset="1" stop-color="#17161b"/></linearGradient></defs><rect x="1.5" y="1.5" width="97" height="31" rx="15.5" fill="url(#p)" stroke="url(#g)" stroke-width="2.6"/><rect x="5" y="4" width="90" height="10" rx="5" fill="#fff" fill-opacity=".07"/></svg>`),
  roundBtn: svgUrl(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 36 36"><defs>${GOLD}<radialGradient id="r" cx=".45" cy=".35" r=".7"><stop offset="0" stop-color="#3f3c46"/><stop offset="1" stop-color="#141218"/></radialGradient></defs><circle cx="18" cy="18" r="16.2" fill="url(#r)" stroke="url(#g)" stroke-width="2.4"/></svg>`),
  sheet: svgUrl(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect width="10" height="10" fill="#0d0b12"/></svg>`),
};

const ICON = {
  crosshair: `<svg viewBox="0 0 24 24" fill="none" stroke="#f0d79a" stroke-width="2"><circle cx="12" cy="12" r="7"/><circle cx="12" cy="12" r="2.2" fill="#f0d79a"/><path d="M12 1v5M12 18v5M1 12h5M18 12h5"/></svg>`,
  jump: `<svg viewBox="0 0 24 24" fill="none" stroke="#f0d79a" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 18c4-1 7-5 9-11"/><path d="M9 6h6v6"/></svg>`,
  bag: `<svg viewBox="0 0 24 24" fill="#f0d79a"><path d="M8 7a4 4 0 0 1 8 0h2.2l1.3 13.5a1.4 1.4 0 0 1-1.4 1.5H5.9a1.4 1.4 0 0 1-1.4-1.5L5.8 7zm2 0h4a2 2 0 0 0-4 0z"/></svg>`,
  quest: `<svg viewBox="0 0 24 24" fill="#f0d79a"><path d="M10.2 3h3.6l-.7 12h-2.2zM12 17.4a2 2 0 1 1 0 4 2 2 0 0 1 0-4z"/></svg>`,
  chat: `<svg viewBox="0 0 24 24" fill="#f0d79a"><path d="M4 4h16a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-8l-5 4v-4H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z"/></svg>`,
  menu: `<svg viewBox="0 0 24 24" fill="#f0d79a"><rect x="4" y="5" width="16" height="2.6" rx="1.3"/><rect x="4" y="10.7" width="16" height="2.6" rx="1.3"/><rect x="4" y="16.4" width="16" height="2.6" rx="1.3"/></svg>`,
  keyboard: `<svg viewBox="0 0 24 24" fill="none" stroke="#f0d79a" stroke-width="1.8" stroke-linecap="round"><rect x="2.5" y="6" width="19" height="12" rx="2"/><path d="M6 10h.01M9.5 10h.01M13 10h.01M16.5 10h.01M6 14h.01M18 14h.01M9 14h6"/></svg>`,
  phone: `<svg viewBox="0 0 24 24" fill="none" stroke="#f0d79a" stroke-width="1.8" stroke-linecap="round"><rect x="6.5" y="2.5" width="11" height="19" rx="2.2"/><path d="M11 18.5h2"/></svg>`,
  tray: `<svg viewBox="0 0 24 24" fill="#f0d79a"><rect x="4" y="4" width="7" height="7" rx="1.6"/><rect x="13" y="4" width="7" height="7" rx="1.6"/><rect x="4" y="13" width="7" height="7" rx="1.6"/><rect x="13" y="13" width="7" height="7" rx="1.6"/></svg>`,
  close: `<svg viewBox="0 0 24 24" fill="none" stroke="#f0d79a" stroke-width="2.6" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>`,
  full: `<svg viewBox="0 0 24 24" fill="none" stroke="#f0d79a" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/></svg>`,
  rotate: `<svg viewBox="0 0 64 64" fill="none" stroke="#f0d79a" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><rect x="20" y="8" width="24" height="40" rx="4"/><path d="M50 30a20 20 0 0 1-18 22M14 34a20 20 0 0 1 18-22"/><path d="M28 56l4-4-4-4M36 8l-4 4 4 4"/></svg>`,
};

// Attack / Interact's face: what a tap would do with the current target. Gold line art like the
// rim; a quest turn-in is the gold "?", a quest to pick up the gold "!", one still in progress grey.
const ARTGOLD = '#f3d98f';
const glyph = (d, w = 1.9, extra = '') => `<svg viewBox="0 0 24 24" fill="none" stroke="${ARTGOLD}" stroke-width="${w}" stroke-linecap="round" stroke-linejoin="round">${d}${extra}</svg>`;
const mark = (ch, color) => `<svg viewBox="0 0 24 24"><text x="12" y="19.5" text-anchor="middle" font-family="'OW Friz', Georgia, serif" font-size="21" font-weight="700" fill="${color}" stroke="#2a1a05" stroke-width="1.1" paint-order="stroke">${ch}</text></svg>`;
const ROLE_ICON = {
  fight: glyph('<path d="M14.5 17.5L3 6V3h3l11.5 11.5"/><path d="M13 19l6-6M16 16l4 4M19 21l2-2"/><path d="M14.5 6.5L18 3h3v3l-3.5 3.5"/><path d="M5 14l4 4M7 17l-3 3M3 19l2 2"/>'),
  loot: glyph('<path d="M9 3h6l-1.6 3h-2.8z"/><path d="M10.4 6C6 8 4 12 4 15.4 4 19 7 21 12 21s8-2 8-5.6C20 12 18 8 13.6 6"/><path d="M14 11.5h-2.6a1.3 1.3 0 0 0 0 2.6h1.2a1.3 1.3 0 0 1 0 2.6H10M12 10v1.5M12 16.7v1.5"/>'),
  talk: glyph('<path d="M4 5h16a1.5 1.5 0 0 1 1.5 1.5v9A1.5 1.5 0 0 1 20 17h-8l-5 4v-4H4a1.5 1.5 0 0 1-1.5-1.5v-9A1.5 1.5 0 0 1 4 5z"/><path d="M8 11h.01M12 11h.01M16 11h.01" stroke-width="2.6"/>'),
  player: glyph('<path d="M11 17l2 2a1 1 0 1 0 3-3"/><path d="M14 14l2.5 2.5a1 1 0 1 0 3-3l-3.9-3.9a3 3 0 0 0-4.2 0l-.9.9a1 1 0 1 1-3-3l2.8-2.8a5.8 5.8 0 0 1 7 .9L21 7.5"/><path d="M21 3l1 11h-2"/><path d="M3 3L2 14l6.5 6.5a1 1 0 1 0 3-3"/><path d="M3 4h8"/>', 1.6),
  quest: mark('!', '#ffd100'),
  turnin: mark('?', '#ffd100'),
  inprogress: mark('?', '#b9b9b9'),
  repair: glyph('<path d="M4 8h12l4-2v4h-3a3 3 0 0 1-3 3h-1v3h3v3H8v-3h3v-3H9a5 5 0 0 1-5-5z"/>'),
  shop: glyph('<path d="M5 8h14l-1 12.5a1.5 1.5 0 0 1-1.5 1.5h-9A1.5 1.5 0 0 1 6 20.5z"/><path d="M9 8V6.5a3 3 0 0 1 6 0V8"/>'),
  train: glyph('<path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v15H6.5A2.5 2.5 0 0 0 4 20.5z"/><path d="M4 20.5A2.5 2.5 0 0 0 6.5 23H20v-5"/><path d="M9 8h7M9 11.5h5"/>'),
  flight: glyph('<path d="M21 3C13 3.5 6.5 8 3 17c3-1.6 6-2 8.5-1.3C9.8 17 9 18.6 9 21c5.5-2.6 10-8.4 12-18z"/><path d="M14 9l-6 6"/>'),
  inn: glyph('<path d="M3 20V8M3 15h18v5M21 15v-3a3 3 0 0 0-3-3h-7v6"/><circle cx="7" cy="11.5" r="2"/>'),
  bank: glyph('<path d="M3 9l9-5 9 5"/><path d="M5 10v8M9.5 10v8M14.5 10v8M19 10v8M3 20.5h18"/>'),
  stable: glyph('<circle cx="11" cy="4.5" r="1.8"/><circle cx="18" cy="8" r="1.8"/><circle cx="20" cy="15" r="1.8"/><path d="M8.5 13.5c1.6-2.2 4.4-2.4 6-.3 1.4 1.9 2.9 3 2.9 5a2.6 2.6 0 0 1-3.3 2.6c-1.3-.4-2.4-.4-3.7 0A2.6 2.6 0 0 1 7 18c0-1.6 0-2.5 1.5-4.5z"/><circle cx="4" cy="8.5" r="1.8"/>'),
  battle: glyph('<path d="M5 21V4M5 4h11l-2 3.5 2 3.5H5"/><path d="M19 21V9"/>'),
  guild: glyph('<path d="M6 3h12v14l-6 4-6-4z"/><path d="M9 8h6M12 8v7"/>'),
  spirit: glyph('<path d="M12 4.5a2 2 0 1 0 .01 0"/><path d="M12 8v6M7 21l5-7 5 7M3 9c3 2 6 2 9 0 3 2 6 2 9 0"/>'),
};
// ...shown as the game's own art wherever it has one: the cursors you see when hovering a unit on
// PC (the sword over an enemy, the loot bags, the speech bubble, the anvil hammer, the trainer's
// book, the flight boot) and the gossip window's icons (the quest "!" and "?", bank, inn, tabard,
// battlemaster, spirit healer). The line art above stays as the fallback while one loads.
const ROLE_TEX = {
  fight: 'Interface\\Cursor\\Attack', loot: 'Interface\\Cursor\\LootAll', talk: 'Interface\\Cursor\\Speak',
  player: 'Interface\\Cursor\\Inspect', shop: 'Interface\\Cursor\\Buy', repair: 'Interface\\Cursor\\Repair',
  train: 'Interface\\Cursor\\Trainer', flight: 'Interface\\Cursor\\Taxi', stable: 'Interface\\Cursor\\Interact',
  quest: 'Interface\\GossipFrame\\AvailableQuestIcon', turnin: 'Interface\\GossipFrame\\ActiveQuestIcon',
  inprogress: 'Interface\\GossipFrame\\ActiveQuestIcon', inn: 'Interface\\GossipFrame\\BinderGossipIcon',
  bank: 'Interface\\GossipFrame\\BankerGossipIcon', guild: 'Interface\\GossipFrame\\TabardGossipIcon',
  battle: 'Interface\\GossipFrame\\BattleMasterGossipIcon', spirit: 'Interface\\GossipFrame\\HealerGossipIcon',
};
const ROLE_SAY = {
  loot: 'Double-tap the body to loot it', talk: 'Double-tap them to talk', player: 'Double-tap them to trade, invite or whisper',
  quest: 'Double-tap them for the quest', turnin: 'Double-tap them to turn your quest in', inprogress: 'Your quest for them is not done yet',
  repair: 'Double-tap them to shop and repair', shop: 'Double-tap them to shop', train: 'Double-tap them to train',
  flight: 'Double-tap them to fly', inn: 'Double-tap them to make this inn your home', bank: 'Double-tap them to open your bank',
  stable: 'Double-tap them for your pets', battle: 'Double-tap them to join a battleground', guild: 'Double-tap them for guild business',
  spirit: 'Double-tap them to come back to life here',
};

// The Menu sheet: one big button per window. `cmd` = a binding fired through the bridge.
const MENU = [
  { label: 'Character', cmd: 'TOGGLECHARACTER0', icon: 'Interface\\Icons\\INV_Chest_Chain_05' },
  { label: 'Spellbook', cmd: 'TOGGLESPELLBOOK', icon: 'Interface\\Icons\\INV_Misc_Book_09' },
  { label: 'Talents', cmd: 'TOGGLETALENTS', icon: 'Interface\\Icons\\Ability_Marksmanship' },
  { label: 'Quest log', cmd: 'TOGGLEQUESTLOG', icon: 'Interface\\Icons\\INV_Misc_Note_01' },
  { label: 'World map', cmd: 'TOGGLEWORLDMAP', icon: 'Interface\\Icons\\INV_Misc_Map_01' },
  { label: 'Social', cmd: 'TOGGLESOCIAL', icon: 'Interface\\Icons\\Spell_Holy_PrayerOfSpirit' },
  { label: 'Bags', cmd: 'OPENALLBAGS', icon: 'Interface\\Icons\\INV_Misc_Bag_08' },
  { label: 'Addons', chat: '/addons', icon: 'Interface\\Icons\\INV_Misc_Gear_01' },
  { label: 'Game menu', cmd: 'TOGGLEGAMEMENU', icon: 'Interface\\Icons\\INV_Misc_QuestionMark' },
];

// -- Styles -------------------------------------------------------------------------------------

function style() {
  if (document.getElementById('ow-touch-style')) return;
  const s = document.createElement('style');
  s.id = 'ow-touch-style';
  s.textContent = `
    @font-face { font-family: 'OW Friz'; src: url('/data/Fonts%5CFRIZQT__.TTF') format('truetype'); font-display: swap; }
    #ow-touch { position: fixed; inset: 0; z-index: 22; pointer-events: none; display: none;
      font-family: 'OW Cinzel', Georgia, serif; -webkit-user-select: none; user-select: none;
      -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; text-rendering: geometricPrecision; font-kerning: normal;
      -webkit-touch-callout: none; -webkit-tap-highlight-color: transparent; }
    #ow-touch.on { display: block; }
    #ow-touch .zone, #ow-touch .ctl { pointer-events: auto; touch-action: none; }
    #ow-touch .world { position: absolute; inset: 0; }
    #ow-touch.mouse .world { pointer-events: none; }
    #ow-touch .stick-zone { position: absolute; left: 0; bottom: 0; width: 42%; height: 62%; }
    #ow-touch .stick { position: absolute; width: 120px; height: 120px; margin: -60px 0 0 -60px;
      background: ${ART.stickBase} center / contain no-repeat; opacity: .55; transition: opacity .15s;
      pointer-events: none; }
    #ow-touch .stick.live { opacity: .95; transition: none; }
    #ow-touch.windows .stick:not(.live) { opacity: .28; }
    #ow-touch .knob { position: absolute; left: 50%; top: 50%; width: 52px; height: 52px; margin: -26px 0 0 -26px;
      background: ${ART.knob} center / contain no-repeat; }
    #ow-touch .pill { position: absolute; display: flex; align-items: center; justify-content: center; gap: 6px;
      background: ${ART.pill} center / 100% 100% no-repeat; color: #f0d79a; font-weight: 600; filter: drop-shadow(0 3px 3px rgba(0, 0, 0, .65));
      text-shadow: 0 1px 2px #000; letter-spacing: .04em; }
    #ow-touch .jump { width: 64px; height: 30px; margin: -15px 0 0 -32px; }
    #ow-touch .jump svg { width: 20px; height: 20px; }
    #ow-touch .rbtn { width: 36px; height: 36px; display: flex; align-items: center; justify-content: center;
      background: ${ART.roundBtn} center / contain no-repeat; filter: drop-shadow(0 3px 3px rgba(0, 0, 0, .65)); }
    #ow-touch .rbtn svg { width: 18px; height: 18px; }
    #ow-touch .target { position: absolute; width: 46px; height: 46px; margin: -23px 0 0 -23px; }
    #ow-touch .target svg { width: 24px; height: 24px; }
    #ow-touch .attack { position: absolute; width: 96px; height: 96px; margin: -48px 0 0 -48px;
      background: ${ART.attack} center / contain no-repeat; display: flex; align-items: center; justify-content: center;
      color: #f6e3a8; font-size: 13px; font-weight: 600; line-height: 1.12; letter-spacing: .03em; text-align: center;
      text-shadow: 0 1px 1px rgba(0, 0, 0, .95), 0 0 2px rgba(0, 0, 0, .6); padding-top: 1px; }
    #ow-touch .attack { filter: drop-shadow(0 4px 4px rgba(0, 0, 0, .6)); }
    #ow-touch .attack .ico { width: 42px; height: 42px; display: flex; filter: drop-shadow(0 1.5px 1px rgba(0, 0, 0, .9)); }
    #ow-touch .attack .ico svg, #ow-touch .attack .ico img { width: 100%; height: 100%; }
    #ow-touch .attack .ico.cursor { width: 46px; height: 46px; margin: 2px 0 0 4px; }   /* cursor art sits up-left in its square */
    #ow-touch .attack .ico.gossip { width: 34px; height: 34px; }
    #ow-touch .attack .ico.dim img { filter: grayscale(1) brightness(.8); }
    /* most cursors carry the little pointer arrow in their top-left corner: trimmed off here */
    #ow-touch .attack .ico.cursor.tip img { clip-path: polygon(34% 0, 100% 0, 100% 100%, 0 100%, 0 34%); }
    /* a hostile target: the label turns ember-red instead of a glow */
    #ow-touch .attack.hostile .ico svg { stroke: #ffb48a; }
    #ow-touch .attack.hostile .ico img { filter: drop-shadow(0 0 3px rgba(255, 90, 40, .7)); }
    #ow-touch .key { position: absolute; width: 48px; height: 48px; margin: -24px 0 0 -24px; border-radius: 50%;
      filter: drop-shadow(0 3px 3px rgba(0, 0, 0, .7)) drop-shadow(0 0 1px rgba(0, 0, 0, .9)); }
    #ow-touch .key .face { position: absolute; inset: 3px; border-radius: 50%; background: ${ART.emptyFace} center / cover; }
    /* depth: a soft top highlight and a shaded lower rim over the icon */
    #ow-touch .key .face::after { content: ''; position: absolute; inset: 0; border-radius: 50%; pointer-events: none;
      background: radial-gradient(ellipse 70% 45% at 38% 22%, rgba(255, 255, 255, .28), rgba(255, 255, 255, 0) 70%);
      box-shadow: inset 0 -4px 7px rgba(0, 0, 0, .55), inset 0 2px 2px rgba(255, 255, 255, .12); }
    /* an empty slot: the stock action bar's dark, recessed socket */
    #ow-touch .key.empty .face { background: radial-gradient(circle at 50% 42%, rgba(66, 62, 70, .62), rgba(14, 13, 17, .86) 74%);
      box-shadow: inset 0 4px 8px rgba(0, 0, 0, .95), inset 0 -1px 2px rgba(255, 255, 255, .1); }
    #ow-touch .key.empty .face::after { background: none; box-shadow: inset 0 0 0 1px rgba(120, 112, 100, .35); }
    #ow-touch .key.empty .ring { opacity: .8; }
    #ow-touch .key .face.icon { background-size: 118%; }
    #ow-touch .key .ring { position: absolute; inset: 0; background: ${ART.ring} center / contain no-repeat; }
    #ow-touch .key .cd { position: absolute; inset: 3px; border-radius: 50%; display: none; align-items: center; justify-content: center;
      color: #fff; font: 700 14px system-ui, sans-serif; text-shadow: 0 1px 2px #000; }
    #ow-touch .key.cooling .cd { display: flex; }
    #ow-touch .key.unusable .face { filter: grayscale(1) brightness(.55); }
    #ow-touch .key.nomana .face { filter: brightness(.6) sepia(1) hue-rotate(185deg) saturate(3); }
    #ow-touch .key.far .face { filter: brightness(.75) sepia(1) hue-rotate(-40deg) saturate(4); }
    #ow-touch .key .count { position: absolute; right: 4px; bottom: 2px; font: 700 11px system-ui, sans-serif; color: #fff; text-shadow: 0 1px 2px #000; }
    #ow-touch .pressed { transform: scale(.92); filter: brightness(1.25); }
    #ow-touch .dots { position: absolute; display: flex; gap: 6px; padding: 7px 9px; margin: -10px 0 0 -24px; border-radius: 13px; background: rgba(12, 10, 8, .55); box-shadow: inset 0 0 0 1px rgba(240, 215, 154, .35); }
    #ow-touch .dots i { width: 7px; height: 7px; border-radius: 50%; background: rgba(240, 215, 154, .3); }
    #ow-touch .dots i.on { background: #f0d79a; }
    #ow-touch .tray { position: absolute; display: flex; flex-direction: row-reverse; align-items: center; gap: 6px; }
    #ow-touch .tray .item { display: none; }
    #ow-touch .tray.open .item { display: flex; animation: ow-slide .16s ease-out both; }
    @keyframes ow-slide { from { opacity: 0; transform: translateX(10px); } }
    #ow-touch .sheet { position: absolute; left: 50%; transform: translateX(-50%); bottom: max(10px, env(safe-area-inset-bottom));
      width: min(560px, 92vw); max-height: 82vh; display: none; flex-direction: column; pointer-events: auto;
      background: rgba(13, 11, 18, .94); border: 1px solid #8a6a2a; box-shadow: inset 0 0 0 1px #3d2c10, 0 10px 40px #000;
      border-radius: 10px; padding: 12px 14px; color: #e8dcc0; font: 14px system-ui, sans-serif; }
    #ow-touch .sheet.open { display: flex; }
    #ow-touch .sheet h3 { margin: 0 0 8px; font: 600 15px 'OW Cinzel', Georgia, serif; color: #f0c058; letter-spacing: .06em; display: flex; justify-content: space-between; align-items: center; }
    #ow-touch .sheet .x { width: 32px; height: 32px; border: 0; background: none; color: #e8dcc0; font-size: 22px; }
    #ow-touch .log { overflow-y: auto; flex: 1 1 auto; min-height: 60px; max-height: 42vh; font-size: 13px; line-height: 1.35; padding-right: 4px; }
    #ow-touch .log div { margin: 1px 0; overflow-wrap: anywhere; }
    #ow-touch .send { display: flex; gap: 8px; margin-top: 8px; }
    #ow-touch .send input { flex: 1; min-width: 0; height: 40px; border-radius: 8px; border: 1px solid #6b5326; background: #07060a; color: #f3ead2; padding: 0 10px; font-size: 16px; }
    #ow-touch .send button, #ow-touch .grid button, #ow-touch .row button { height: 40px; padding: 0 14px; border-radius: 8px; border: 1px solid #9b7a33;
      background: linear-gradient(#3a2f1a, #1d170c); color: #f0d79a; font: 600 13px 'OW Cinzel', Georgia, serif; letter-spacing: .04em; }
    #ow-touch .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(98px, 1fr)); gap: 8px; overflow-y: auto; }
    #ow-touch .grid button { height: 74px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 5px; padding: 6px; }
    #ow-touch .grid img:not([src]) { visibility: hidden; }
    #ow-touch .grid img { width: 34px; height: 34px; border-radius: 6px; box-shadow: 0 0 0 1px #9b7a33; }
    #ow-touch .row { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px; }
    #ow-touch .row button { flex: 1 1 auto; font-size: 12px; }
    #ow-touch .badge { position: absolute; right: -2px; top: -2px; width: 11px; height: 11px; border-radius: 50%;
      background: #e0402c; box-shadow: 0 0 0 1.5px #1a0d08; display: none; }
    #ow-touch .badge.on { display: block; }
    #ow-touch .closer { left: 50%; top: 8px; height: 34px; padding: 0 16px 0 12px; transform: translateX(-50%); font-size: 13px; }
    #ow-touch .closer svg { width: 14px; height: 14px; }
    #ow-touch .closer:not(.on) { display: none; }
    #ow-touch .strip { position: absolute; display: flex; gap: 8px; transform: translateX(-50%); }
    #ow-touch .strip:empty { display: none; }
    #ow-touch .sbtn { position: relative; width: 40px; height: 40px; border-radius: 50%;
      filter: drop-shadow(0 3px 3px rgba(0, 0, 0, .7)); }
    #ow-touch .sbtn .face { position: absolute; inset: 3px; border-radius: 50%; background: ${ART.emptyFace} center / 118%; }
    #ow-touch .sbtn .ring { position: absolute; inset: 0; background: ${ART.ring} center / contain no-repeat; }
    #ow-touch .sbtn.active .ring { filter: brightness(1.45) drop-shadow(0 0 4px rgba(255, 220, 120, .9)); }
    #ow-touch .sbtn.auto::after { content: ''; position: absolute; inset: -3px; border-radius: 50%; border: 1.5px dashed rgba(255, 220, 120, .85); }
    #ow-touch .sbtn.off .face { filter: grayscale(1) brightness(.55); }
    #ow-touch .gap { width: 10px; }
    #ow-touch .typebar { position: absolute; left: 50%; top: 50px; transform: translateX(-50%); width: min(520px, 86vw); display: none;
      gap: 6px; padding: 6px; border-radius: 10px; background: rgba(13, 11, 18, .94); border: 1px solid #8a6a2a; pointer-events: auto;
      box-shadow: 0 6px 24px #000; }
    #ow-touch .typebar.on { display: flex; }
    #ow-touch .typebar input { flex: 1; min-width: 0; height: 40px; border-radius: 8px; border: 1px solid #6b5326; background: #07060a; color: #f3ead2; padding: 0 10px; font-size: 16px; }
    #ow-touch .typebar button { height: 40px; padding: 0 12px; border-radius: 8px; border: 1px solid #9b7a33; background: linear-gradient(#3a2f1a, #1d170c); color: #f0d79a; font: 600 13px 'OW Cinzel', Georgia, serif; }
    #ow-touch .info { position: absolute; left: 50%; top: 52%; transform: translate(-50%, -50%); width: min(340px, 60vw); display: none; flex-direction: column; gap: 8px;
      padding: 10px 12px; border-radius: 10px; background: rgba(13, 11, 18, .95); border: 1px solid #8a6a2a; box-shadow: 0 8px 28px #000;
      color: #e8dcc0; font: 13px/1.35 system-ui, sans-serif; pointer-events: auto; }
    #ow-touch .info.on { display: flex; }
    #ow-touch .info.fresh { pointer-events: none; }
    #ow-touch.sheet-open .strip, #ow-touch.sheet-open .closer, #ow-touch.sheet-open .typebar, #ow-touch.sheet-open .info { display: none !important; }
    #ow-touch .info .t { white-space: pre-wrap; max-height: 40vh; overflow-y: auto; }
    #ow-touch .info .t b { color: #f0c058; font: 600 14px 'OW Cinzel', Georgia, serif; }
    #ow-touch .info .b { display: flex; gap: 6px; flex-wrap: wrap; }
    #ow-touch .info button, #ow-touch .settings button { flex: 1 1 auto; height: 36px; padding: 0 10px; border-radius: 8px; border: 1px solid #9b7a33;
      background: linear-gradient(#3a2f1a, #1d170c); color: #f0d79a; font: 600 12px 'OW Cinzel', Georgia, serif; }
    #ow-touch .settings { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 8px; }
    #ow-touch .kbd { position: absolute; right: 12px; top: 12px; display: none; pointer-events: auto; }
    #ow-touch.glue-type .kbd { display: flex; }
    #ow-touch .ghost { position: absolute; left: -9999px; top: 0; width: 10px; height: 10px; opacity: 0; }
    #ow-touch .opts { display: flex; flex-direction: column; gap: 8px; overflow-y: auto; }
    #ow-touch .opt { text-align: left; padding: 9px 12px; border-radius: 8px; border: 1px solid #5d4720; background: rgba(40, 32, 18, .55);
      color: #e8dcc0; font: 13px/1.35 system-ui, sans-serif; }
    #ow-touch .opt b { display: block; color: #f0d79a; font: 600 14px 'OW Cinzel', Georgia, serif; letter-spacing: .03em; margin-bottom: 2px; }
    #ow-touch .opt.sel { border-color: #f0c058; box-shadow: 0 0 0 1px #f0c058 inset, 0 0 12px rgba(240, 192, 88, .25); background: rgba(70, 52, 20, .6); }
    #ow-touch .opt.sel b::after { content: '  ✓'; color: #f0c058; }
    #ow-touch table.vs { width: 100%; border-collapse: collapse; margin-top: 10px; font: 12px/1.3 system-ui, sans-serif; }
    #ow-touch table.vs th { text-align: left; color: #f0c058; font: 600 12px 'OW Cinzel', Georgia, serif; padding: 4px 6px; border-bottom: 1px solid #5d4720; }
    #ow-touch table.vs td { padding: 4px 6px; border-bottom: 1px solid rgba(93, 71, 32, .45); vertical-align: top; }
    #ow-touch table.vs td:first-child { color: #c9b98f; white-space: nowrap; }
    #ow-touch .restore { position: absolute; right: 8px; top: 46%; display: none; pointer-events: auto; opacity: .75; }
    #ow-touch.pcmode { display: block; }
    #ow-touch.pcmode .restore { display: flex; }
    #ow-touch.pcmode > :not(.restore):not(.toast):not(.sheet) { display: none !important; }
    #ow-touch .toast { position: absolute; left: 50%; top: 28%; transform: translateX(-50%); padding: 8px 14px; border-radius: 8px;
      background: rgba(10, 8, 16, .88); border: 1px solid #8a6a2a; color: #f0d79a; font: 600 13px 'OW Cinzel', Georgia, serif;
      opacity: 0; transition: opacity .3s; pointer-events: none; text-align: center; max-width: 80vw; }
    #ow-touch .toast.on { opacity: 1; }
    #ow-touch .rotate { position: absolute; inset: 0; display: none; flex-direction: column; align-items: center; justify-content: center; gap: 14px;
      background: rgba(5, 4, 10, .92); color: #f0d79a; font: 600 16px 'OW Cinzel', Georgia, serif; letter-spacing: .06em; pointer-events: auto; }
    #ow-touch .rotate svg { width: 64px; height: 64px; }
    /* a phone held upright: the game's screens are laid out for landscape (character creation's
       panels pile up over its buttons), so every game screen asks to be turned sideways */
    @media (orientation: portrait) { #ow-touch.on.ingame.phone .rotate { display: flex; } }
    #ow-touch .rotate .go, #ow-touch .fsgo .go { margin-top: 4px; padding: 11px 22px; border-radius: 22px; border: 1px solid #c9a24a;
      background: linear-gradient(#4a3a1c, #21190b); color: #ffd98a; font: 600 15px 'OW Cinzel', Georgia, serif; letter-spacing: .05em;
      box-shadow: 0 4px 14px rgba(0, 0, 0, .6); }
    #ow-touch:not(.canfs) .rotate .go { display: none; }
    #ow-touch .rotate .sub, #ow-touch .fsgo .sub { font: 13px system-ui, sans-serif; color: #c9b98f; letter-spacing: 0; max-width: 80vw; text-align: center; }
    /* sideways but not full screen yet: one tap goes full screen (the browser only allows it from a tap) */
    #ow-touch .fsgo { position: absolute; inset: 0; display: none; flex-direction: column; align-items: center; justify-content: center; gap: 10px;
      background: rgba(5, 4, 10, .72); color: #f0d79a; font: 600 17px 'OW Cinzel', Georgia, serif; letter-spacing: .05em; pointer-events: auto; }
    #ow-touch .fsgo svg { width: 46px; height: 46px; }
    #ow-touch .fsgo .skip { margin-top: 2px; padding: 8px 14px; border: 0; background: none; color: #a99a78; font: 13px system-ui, sans-serif; text-decoration: underline; }
    @media (orientation: landscape) { #ow-touch.on.ingame.phone.canfs.wantfs:not(.pcmode) .fsgo { display: flex; } }
    #ow-touch:not(.inworld) .play, #ow-touch.loading .play { display: none; }
    /* character / realm screens: taps become corrected mouse clicks (the game ignores raw touches there) */
    #ow-touch .glue { position: absolute; inset: 0; display: none; }
    /* the aiming loupe: what is under the finger, magnified, above it */
    #ow-touch .loupe { position: absolute; width: 132px; height: 132px; border-radius: 50%; display: none; pointer-events: none; overflow: hidden;
      border: 3px solid #d9b25a; box-shadow: 0 0 0 1px #000, 0 8px 22px rgba(0, 0, 0, .7); background: #000; z-index: 2; }
    #ow-touch .loupe.on { display: block; }
    #ow-touch .loupe canvas { width: 100%; height: 100%; display: block; }
    /* where each click went: a small gold ring that fades */
    #ow-touch .tapring { position: absolute; width: 26px; height: 26px; margin: -13px 0 0 -13px; border-radius: 50%; pointer-events: none;
      border: 2px solid #ffd76a; box-shadow: 0 0 8px rgba(255, 200, 80, .8); opacity: 0; z-index: 2; }
    #ow-touch .tapring.go { animation: ow-ring .45s ease-out; }
    #ow-touch .tapring.snap { border-color: #7dff9a; box-shadow: 0 0 8px rgba(120, 255, 150, .8); }
    @keyframes ow-ring { from { opacity: 1; transform: scale(.5); } to { opacity: 0; transform: scale(1.5); } }
    #ow-touch .tdebug { position: absolute; left: 6px; bottom: 6px; display: none; padding: 4px 7px; border-radius: 4px; pointer-events: none;
      background: rgba(0, 0, 0, .75); color: #9f9; font: 11px/1.3 ui-monospace, monospace; white-space: pre; z-index: 3; }
    #ow-touch.debug .tdebug { display: block; }
    #ow-touch.glue-touch:not(.inworld):not(.loading) .glue { display: block; }
    /* panels in the look of the Classic+ Quests tracker: near-black glass, a hairline bronze
       border, a slim header strip, gold titles in the game's own Friz Quadrata */
    #ow-touch .sheet, #ow-touch .info, #ow-touch .typebar, #ow-touch .toast {
      background: rgba(8, 8, 10, .8); border: 1px solid rgba(150, 132, 96, .5); border-radius: 3px;
      box-shadow: 0 6px 22px rgba(0, 0, 0, .6); color: #fff; font-family: 'OW Friz', Georgia, serif; }
    #ow-touch .sheet { padding: 0 0 10px; }
    #ow-touch .sheet > :not(h3) { margin-left: 10px; margin-right: 10px; }
    #ow-touch .sheet h3 { margin: 0 0 8px; padding: 5px 6px 5px 10px; font: 14px 'OW Friz', Georgia, serif; letter-spacing: 0;
      color: #ffd100; text-shadow: 0 1px 1px #000; background: linear-gradient(rgba(255, 255, 255, .09), rgba(255, 255, 255, .03));
      border-bottom: 1px solid rgba(150, 132, 96, .4); }
    #ow-touch .sheet .x { width: 28px; height: 24px; font-size: 18px; color: #c9c1b2; }
    #ow-touch .send button, #ow-touch .grid button, #ow-touch .row button, #ow-touch .info button,
    #ow-touch .settings button, #ow-touch .typebar button { border-radius: 3px; border: 1px solid rgba(150, 132, 96, .5);
      background: rgba(255, 255, 255, .05); color: #ffd100; font: 13px 'OW Friz', Georgia, serif; letter-spacing: 0; text-shadow: 0 1px 1px #000; }
    #ow-touch .grid button span { color: #fff; }
    #ow-touch .grid img { border-radius: 2px; box-shadow: 0 0 0 1px rgba(150, 132, 96, .7); }
    #ow-touch .send input, #ow-touch .typebar input { border-radius: 3px; border: 1px solid rgba(150, 132, 96, .5);
      background: rgba(0, 0, 0, .6); color: #fff; font: 16px 'OW Friz', Georgia, serif; }
    #ow-touch .log { font: 13px/1.35 'OW Friz', Georgia, serif; }
    #ow-touch .toast { font: 13px 'OW Friz', Georgia, serif; color: #ffd100; text-shadow: 0 1px 1px #000; padding: 7px 12px; }
    #ow-touch .info { font: 13px/1.35 'OW Friz', Georgia, serif; }
    #ow-touch .info .t b { font: 15px 'OW Friz', Georgia, serif; color: #ffd100; }
    #ow-touch .opt { border-radius: 3px; border: 1px solid rgba(150, 132, 96, .45); background: rgba(255, 255, 255, .04);
      color: #e9e4da; font: 13px/1.35 'OW Friz', Georgia, serif; }
    #ow-touch .opt b { font: 14px 'OW Friz', Georgia, serif; color: #ffd100; letter-spacing: 0; }
    #ow-touch .opt.sel { border-color: #ffd100; box-shadow: inset 0 0 0 1px rgba(255, 209, 0, .6); background: rgba(255, 209, 0, .07); }
    #ow-touch .opt.sel b::after { color: #ffd100; }
    #ow-touch table.vs { font: 12px/1.3 'OW Friz', Georgia, serif; }
    #ow-touch table.vs th { font: 12px 'OW Friz', Georgia, serif; color: #ffd100; border-bottom-color: rgba(150, 132, 96, .5); }
    #ow-touch table.vs td { border-bottom-color: rgba(150, 132, 96, .22); }
    #ow-touch table.vs td:first-child { color: #ffd100; }
    #ow-touch .pill { font-family: 'OW Friz', Georgia, serif; font-weight: 400; letter-spacing: 0; }
    /* the page menu handle moves to the bottom edge, out of the target frame's way */
    body.ow-touch-world #ow-dock { top: auto; bottom: 0; flex-direction: column-reverse; }
    body.ow-touch-world #ow-dock-handle { border-radius: 8px 8px 0 0; border-top: 1px solid rgba(201,162,39,.35); border-bottom: 0; }
  `;
  document.head.append(s);
}

// -- BLP icons (the game's own art for the action keys and the menu) -----------------------------

const iconCache = new Map();

function dxtColors(c0, c1, out, opaque) {
  const r = (c) => [((c >> 11) & 31) * 255 / 31, ((c >> 5) & 63) * 255 / 63, (c & 31) * 255 / 31];
  const a = r(c0), b = r(c1);
  out[0] = [...a, 255]; out[1] = [...b, 255];
  if (c0 > c1 || opaque) {
    out[2] = [(2 * a[0] + b[0]) / 3, (2 * a[1] + b[1]) / 3, (2 * a[2] + b[2]) / 3, 255];
    out[3] = [(a[0] + 2 * b[0]) / 3, (a[1] + 2 * b[1]) / 3, (a[2] + 2 * b[2]) / 3, 255];
  } else {
    out[2] = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2, 255];
    out[3] = [0, 0, 0, 0];
  }
}

/** Decode a BLP2 (palette, DXT1/3/5 or raw BGRA) to RGBA. */
export function decodeBlp(buf) {
  const v = new DataView(buf), u8 = new Uint8Array(buf);
  if (String.fromCharCode(u8[0], u8[1], u8[2], u8[3]) !== 'BLP2') throw new Error('not BLP2');
  const comp = u8[8], alphaDepth = u8[9], alphaType = u8[10];
  const w = v.getUint32(12, true), h = v.getUint32(16, true);
  const off = v.getUint32(20, true);
  const px = new Uint8ClampedArray(w * h * 4);
  if (comp === 1) {
    const pal = 148;
    for (let i = 0; i < w * h; i++) {
      const p = pal + u8[off + i] * 4;
      px[i * 4] = u8[p + 2]; px[i * 4 + 1] = u8[p + 1]; px[i * 4 + 2] = u8[p]; px[i * 4 + 3] = 255;
    }
    const ao = off + w * h;
    if (alphaDepth === 8) for (let i = 0; i < w * h; i++) px[i * 4 + 3] = u8[ao + i];
    else if (alphaDepth === 1) for (let i = 0; i < w * h; i++) px[i * 4 + 3] = (u8[ao + (i >> 3)] >> (i & 7)) & 1 ? 255 : 0;
    else if (alphaDepth === 4) for (let i = 0; i < w * h; i++) px[i * 4 + 3] = ((u8[ao + (i >> 1)] >> ((i & 1) * 4)) & 15) * 17;
  } else if (comp === 2) {
    const kind = alphaDepth <= 1 ? 1 : (alphaType === 7 ? 5 : 3);
    const bs = kind === 1 ? 8 : 16;
    let p = off;
    const cols = [[], [], [], []];
    for (let by = 0; by < h; by += 4) {
      for (let bx = 0; bx < w; bx += 4) {
        const alpha = new Array(16).fill(255);
        if (kind === 3) {
          for (let i = 0; i < 16; i++) alpha[i] = ((u8[p + (i >> 1)] >> ((i & 1) * 4)) & 15) * 17;
        } else if (kind === 5) {
          const a0 = u8[p], a1 = u8[p + 1];
          const t = [a0, a1];
          if (a0 > a1) for (let i = 1; i < 7; i++) t.push(((7 - i) * a0 + i * a1) / 7);
          else { for (let i = 1; i < 5; i++) t.push(((5 - i) * a0 + i * a1) / 5); t.push(0, 255); }
          let bits = 0n;
          for (let i = 0; i < 6; i++) bits |= BigInt(u8[p + 2 + i]) << BigInt(8 * i);
          for (let i = 0; i < 16; i++) alpha[i] = t[Number((bits >> BigInt(3 * i)) & 7n)];
        }
        const cp = kind === 1 ? p : p + 8;
        const c0 = v.getUint16(cp, true), c1 = v.getUint16(cp + 2, true);
        dxtColors(c0, c1, cols, kind !== 1);
        const idx = v.getUint32(cp + 4, true);
        for (let i = 0; i < 16; i++) {
          const x = bx + (i & 3), y = by + (i >> 2);
          if (x >= w || y >= h) continue;
          const c = cols[(idx >> (2 * i)) & 3];
          const o = (y * w + x) * 4;
          px[o] = c[0]; px[o + 1] = c[1]; px[o + 2] = c[2];
          px[o + 3] = kind === 1 ? c[3] : alpha[i];
        }
        p += bs;
      }
    }
  } else if (comp === 3) {
    for (let i = 0; i < w * h; i++) {
      px[i * 4] = u8[off + i * 4 + 2]; px[i * 4 + 1] = u8[off + i * 4 + 1]; px[i * 4 + 2] = u8[off + i * 4]; px[i * 4 + 3] = u8[off + i * 4 + 3];
    }
  } else throw new Error('BLP compression ' + comp);
  return { w, h, px };
}

/** A game icon ("Interface\\Icons\\X") as a data URL, from the game's own data. */
export function iconUrl(path) {
  if (!path) return Promise.resolve(null);
  const key = path.toLowerCase();
  if (iconCache.has(key)) return iconCache.get(key);
  const p = (async () => {
    const r = await fetch('/data/' + encodeURIComponent(path.replace(/\//g, '\\') + (/\.blp$/i.test(path) ? '' : '.blp')), { credentials: 'same-origin' });
    if (!r.ok) return null;
    const { w, h, px } = decodeBlp(await r.arrayBuffer());
    const c = document.createElement('canvas');
    c.width = w; c.height = h;
    c.getContext('2d').putImageData(new ImageData(px, w, h), 0, 0);
    return c.toDataURL('image/png');
  })().catch(() => null);
  iconCache.set(key, p);
  return p;
}

// The box that has the keyboard: 1.12 has no GetCurrentKeyBoardFocus in this client, so every
// EditBox is hooked (OnEditFocusGained/Lost) to remember it; FOCUS_HOOK runs again every few
// seconds for boxes made later.
const FOCUS = '((GetCurrentKeyBoardFocus and GetCurrentKeyBoardFocus()) or (__OWTOUCH and __OWTOUCH.focusFrame))';
const FOCUS_HOOK = `if not __OWTOUCH then __OWTOUCH = { hidden = {}, orig = {} } end
local T = __OWTOUCH
T.hooked = T.hooked or {}
local f = EnumerateFrames()
while f do
  if f.GetObjectType and f:GetObjectType() == "EditBox" and not T.hooked[f] then
    T.hooked[f] = true
    local g, l = f:GetScript("OnEditFocusGained"), f:GetScript("OnEditFocusLost")
    f:SetScript("OnEditFocusGained", function() T.focusFrame = this if g then g() end end)
    f:SetScript("OnEditFocusLost", function() if T.focusFrame == this then T.focusFrame = nil end if l then l() end end)
  end
  f = EnumerateFrames(f)
end`;

// The action slot behind touch key n (1-12): the stance/stealth bonus bar on page 1, else the page.
const SLOT_FN = `local o = GetBonusBarOffset and GetBonusBarOffset() or 0
local pg = CURRENT_ACTIONBAR_PAGE or 1
local np = NUM_ACTIONBAR_PAGES or 6
local function slot(i) if o > 0 and pg == 1 then return i + (np + o - 1) * 12 end return i + (pg - 1) * 12 end`;

// -- Synthetic mouse on the game ----------------------------------------------------------------

function gameCanvas() { return document.getElementById('benilla') || document.querySelector('canvas'); }

// Where a pointer lands in the client: it multiplies the page position by devicePixelRatio and
// reads that as a pixel of its drawing buffer. Measured both ways (17 Oct 2026):
//   * a real Android phone, pixel ratio 2.625: the buffer is full resolution (2400x1080 for a
//     914x411 page), so the product already lands right: factor 1.0 (2.63 sent taps to 38% of
//     where the finger was);
//   * a page-sized buffer (desktop Chrome's phone emulation, some scaled desktops), pixel ratio 2:
//     every tap landed at double its place: factor 2.
// One rule covers both, per axis: pixel ratio x page size / buffer size. ?tapscale=<n> forces a
// factor for testing another device. ow/input.js uses the same rule.
export function pointerFactor(c) {
  const q = new URLSearchParams(location.search).get('tapscale');
  if (q && Number(q) > 0) return [Number(q), Number(q)];
  const dpr = window.devicePixelRatio || 1;
  if (!c || !c.width || !c.height || !c.clientWidth || !c.clientHeight) return [dpr, dpr];
  return [dpr * c.clientWidth / c.width, dpr * c.clientHeight / c.height];
}

// How a tap reaches the game (?tapmode=, for finding what a device's browser accepts):
//   pointer  (default) mouse-type pointer events, pointer 1
//   both     the same, each followed by the matching classic mouse event
//   touchid  press and release sent while the finger is still down, as the finger's own pointer
export const TAPMODE = (new URLSearchParams(location.search).get('tapmode') || 'pointer').toLowerCase();
let tapPid = 1;
// what the game did with the last events sent ('h' = it handled them, '-' = it didn't), for owdiag
export const tapTrace = { last: '', errors: 0, error: '' };
addEventListener('error', (e) => { tapTrace.errors += 1; tapTrace.error = String(e.message || '').slice(0, 80); });
addEventListener('unhandledrejection', (e) => { tapTrace.errors += 1; tapTrace.error = String(e.reason?.message || e.reason || '').slice(0, 80); });
const MOUSE_TWIN = { pointermove: 'mousemove', pointerdown: 'mousedown', pointerup: 'mouseup' };


function mouse(type, x, y, button, buttons) {
  const c = gameCanvas();
  if (!c) return;
  const r = c.getBoundingClientRect();
  const [fx, fy] = pointerFactor(c);
  const at = { clientX: r.left + (x - r.left) / fx, clientY: r.top + (y - r.top) / fy };
  const kept = c.dispatchEvent(gamePointerEvent(c, type, {
    bubbles: true, cancelable: true, composed: true, pointerId: tapPid, pointerType: 'mouse', isPrimary: true,
    button, buttons, ...at,
  }));
  let mark = (type === 'pointermove' ? 'm' : type === 'pointerdown' ? 'd' : 'u') + (kept ? '-' : 'h');
  if (TAPMODE === 'both' && MOUSE_TWIN[type]) {
    const k2 = c.dispatchEvent(new MouseEvent(MOUSE_TWIN[type], { bubbles: true, cancelable: true, composed: true,
      button: Math.max(0, button), buttons, ...at, view: window, detail: type === 'pointermove' ? 0 : 1 }));
    mark += k2 ? '-' : 'h';
  }
  if (type !== 'pointermove' || !tapTrace.last.endsWith(mark)) tapTrace.last = (tapTrace.last + ' ' + mark).slice(-24);
}
const moveTo = (x, y, buttons = 0) => mouse('pointermove', x, y, -1, buttons);
// A thumb rolls while it's down: up to TAP_SLOP css px of travel is still a tap, and a short, quick
// gesture that did turn into a drag (SLOPPY_PX, SLOPPY_MS) still ends as a click where it landed.
const TAP_SLOP = 20, SLOPPY_PX = 32, SLOPPY_MS = 450;
const LONG_MS = 500;   // a press held this long is a long-press (hover, tooltips), as on Android
const sloppyTap = (t, x, y) => Math.hypot(x - t.x0, y - t.y0) <= SLOPPY_PX && performance.now() - t.t0 < SLOPPY_MS;
// The game reads the cursor once a frame and only presses what the last frame saw under it, so
// each step waits for a frame the game has drawn (a timer alone can fall inside one slow frame).
const afterFrame = () => new Promise((ok) => requestAnimationFrame(() => setTimeout(ok, 0)));
const wait = (ms) => new Promise((ok) => setTimeout(ok, ms));
// A frame the browser drew is not a frame the game ran: on a slow phone the game's update can
// lag the page's animation frame, so a move and the press after it landed in ONE game update,
// the press read the hover from before the move, and the button lit up but never clicked
// ("highlights, no action", Android Chrome on the character screens, 2026-10-24). A Lua call
// through the bridge is answered from inside a game update, so each answer proves the game has
// run once more since the call: two of them = the move is in and the hover it made is computed.
// Falls back to the frame wait when there is no VM (loading screens) or the bridge is slow.
async function gameTicks(n = 2) {
  const w = window.wenilla;
  for (let i = 0; i < n; i++) {
    // whichever comes first: the game's answer, or two page frames (no VM, or a bridge that is busy)
    const frames = afterFrame().then(afterFrame);
    await (w?.lua ? Promise.race([w.lua('return 1', 1500).catch(() => frames), frames]) : frames);
  }
}
const settle = () => gameTicks(2);
// One synthetic mouse sequence at a time: a second tap that lands while the first one's press and
// release are still going (two quick taps on Next, a slow phone) waits its turn instead of
// interleaving its move and press with the first's, which the game read as presses on nothing.
let mouseChain = Promise.resolve();
const inTurn = (fn) => (mouseChain = mouseChain.then(fn, fn));
function click(x, y, button = 0) {
  return inTurn(async () => {
    const bits = button === 2 ? 2 : 1;
    moveTo(x, y);
    await settle();                                  // the game has the cursor there and has hovered it
    mouse('pointerdown', x, y, button, bits);
    await settle();
    mouse('pointerup', x, y, button, 0);
  });
}

// -- The controller -----------------------------------------------------------------------------

export function installTouch(wenilla) {
  if (window.owTouch) return window.owTouch;
  const status = (window.owTouch = { on: false, inworld: false, presses: 0, taps: 0, drags: 0, errors: 0, layout: null });
  if (!wenilla?.hold || !wenilla?.fire) { status.state = 'no-bridge'; return status; }
  style();
  const root = document.createElement('div');
  root.id = 'ow-touch';
  root.innerHTML = `
    <div class="zone glue"></div>
    <div class="loupe"><canvas width="264" height="264"></canvas></div>
    <div class="tapring"></div>
    <div class="tdebug"></div>
    <div class="zone world play"></div>
    <div class="zone stick-zone play"></div>
    <div class="stick play"><div class="knob"></div></div>
    <div class="ctl rbtn target play" aria-label="Target nearest enemy">${ICON.crosshair}</div>
    <div class="ctl attack play" aria-label="Attack"><span class="ico">${ROLE_ICON.fight}</span></div>
    ${[0, 1, 2, 3].map((i) => `<div class="ctl key play" data-k="${i}"><div class="face"></div><div class="ring"></div><div class="cd"></div><div class="count"></div></div>`).join('')}
    <div class="ctl dots play" aria-label="Next actions"><i class="on"></i><i></i><i></i></div>
    <div class="ctl pill jump play" aria-label="Jump">${ICON.jump}</div>
    <div class="tray play">
      <div class="ctl rbtn handle" aria-label="Bags, quests, chat and menu"><span class="hico">${ICON.tray}</span><i class="badge"></i></div>
      <div class="ctl rbtn item" data-act="bags" aria-label="Bags">${ICON.bag}</div>
      <div class="ctl rbtn item" data-act="quests" aria-label="Quests">${ICON.quest}</div>
      <div class="ctl rbtn item" data-act="chat" aria-label="Chat">${ICON.chat}<i class="badge"></i></div>
      <div class="ctl rbtn item" data-act="menu" aria-label="Menu">${ICON.menu}</div>
    </div>
    <div class="sheet chat"><h3>Chat <button class="x" aria-label="Close">&times;</button></h3>
      <div class="log"></div>
      <form class="send"><input enterkeyhint="send" autocomplete="off" placeholder="Say something, or /command"><button>Send</button></form></div>
    <div class="sheet menu"><h3>Menu <button class="x" aria-label="Close">&times;</button></h3>
      <div class="grid">${MENU.map((m, i) => `<button data-m="${i}"><img alt=""><span>${m.label}</span></button>`).join('')}</div>
      <div class="row"><button data-x="full">Full screen</button><button data-x="site">Site menu</button><button data-x="off">Hide touch controls</button></div>
    <div class="settings">
        <button data-s="controls">Controls…</button><button data-s="loot">Auto loot: on</button>
        <button data-s="smaller">Interface −</button><button data-s="bigger">Interface +</button></div>
    </div>
    <div class="sheet controls"><h3>Controls <button class="x" aria-label="Close">&times;</button></h3>
      <div class="opts">
        <button class="opt" data-scheme="classic"><b>Classic</b>Stick walks and strafes. Drag the world to turn your character and the camera together, like holding the right mouse button on PC. Best for fighting.</button>
        <button class="opt" data-scheme="simple"><b>Simple</b>Stick walks and turns, like W A S D's turn keys. Drag the world to look around without turning; the camera swings back behind you as you walk. Easiest to learn.</button>
        <button class="opt" data-scheme="pc"><b>Keyboard &amp; mouse</b>No touch controls; the normal PC interface with its action bars and chat. For a tablet with a keyboard, or a phone on a controller. The small phone button in the corner brings touch back.</button>
        <table class="vs"><tr><th></th><th>Phone</th><th>PC</th></tr>
          <tr><td>Move</td><td>Left stick (double-tap it: auto-run)</td><td>W A S D, Num Lock</td></tr>
          <tr><td>Turn / camera</td><td>Drag the world · pinch to zoom</td><td>Hold right / left mouse · wheel</td></tr>
          <tr><td>Target</td><td>Tap them, or the ⌖ button (hold it to clear)</td><td>Click, Tab</td></tr>
          <tr><td>Talk, loot, use</td><td>Double-tap them</td><td>Right-click</td></tr>
          <tr><td>Attack</td><td>Attack / Interact</td><td>Right-click the enemy</td></tr>
          <tr><td>Abilities</td><td>Four keys; swipe them for more. Hold one for its details, move or remove it</td><td>1 – 0, - and =</td></tr>
          <tr><td>New ability on a key</td><td>Drag it out of the Spellbook, then tap a key</td><td>Drag it onto the bar</td></tr>
          <tr><td>Tooltips</td><td>Touch and hold</td><td>Hover</td></tr>
          <tr><td>Bags, quests, chat, menu</td><td>The corner tray</td><td>B, L, Enter, Esc</td></tr>
          <tr><td>Close windows</td><td>The Close button at the top</td><td>Esc</td></tr>
          <tr><td>Type in a box</td><td>Tap the bar that appears at the top</td><td>Just type</td></tr></table>
      </div></div>
    <div class="ctl rbtn restore" aria-label="Touch controls">${ICON.phone}</div>
    <div class="ctl pill closer play" aria-label="Close windows">${ICON.close}<span>Close</span></div>
    <div class="strip play"></div>
    <form class="typebar"><input enterkeyhint="go" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="Tap here to type"><button type="submit">Enter</button><button type="button" class="tb-x" aria-label="Stop typing">&times;</button></form>
    <div class="info"><div class="t"></div><div class="b"></div></div>
    <div class="ctl rbtn kbd" aria-label="Keyboard">${ICON.keyboard}</div>
    <input class="ghost" autocomplete="off" autocapitalize="off" spellcheck="false" aria-hidden="true">
    <div class="toast"></div>
    <div class="fsgo">${ICON.full}<div>Tap to play full screen</div><button type="button" class="skip">Not now</button></div>
    <div class="rotate">${ICON.rotate}<div>Turn your phone sideways</div><div class="sub">The game is laid out for landscape</div><button type="button" class="go">Play full screen</button></div>`;
  document.body.append(root);
  const $ = (s) => root.querySelector(s);
  const $$ = (s) => [...root.querySelectorAll(s)];
  const stick = $('.stick'), knob = $('.knob'), keys = $$('.key'), attack = $('.attack'), dots = $$('.dots i');

  let toastTimer = 0;
  const toast = (text, ms = 2600) => {
    const t = $('.toast');
    t.textContent = text;
    t.classList.add('on');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.classList.remove('on'), ms);
  };
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const buzz = () => { try { navigator.vibrate?.(8); } catch { /* none */ } };
  const lua = (chunk) => wenilla.lua(chunk, 3000).catch(() => { status.errors += 1; return []; });

  // ---- layout (CSS positions from the spec, inside the safe area) --------------------------------
  const SAFE = { l: 0, r: 0, t: 0, b: 0 };
  const STICK_HOME = { left: 24, bottom: 24, size: 120 };
  function layout() {
    const cs = getComputedStyle(document.documentElement);
    const env = (k) => parseFloat(cs.getPropertyValue(k)) || 0;
    SAFE.l = env('--ow-sl'); SAFE.r = env('--ow-sr'); SAFE.t = env('--ow-st'); SAFE.b = env('--ow-sb');
    const W = innerWidth, H = innerHeight;
    const home = { x: SAFE.l + STICK_HOME.left + 60, y: H - SAFE.b - STICK_HOME.bottom - 60 };
    stick.dataset.hx = home.x; stick.dataset.hy = home.y;
    if (!stick.classList.contains('live')) { stick.style.left = home.x + 'px'; stick.style.top = home.y + 'px'; }
    // right-thumb cluster: Attack 20 px in from the right, its arc pivoting toward the corner
    const ax = W - SAFE.r - 20 - 40, ay = H - SAFE.b - 40 - 38;
    attack.style.left = ax + 'px'; attack.style.top = ay + 'px';
    // the reticle sits straight above Attack, the four ability keys continue the same arc to the left
    const at = (deg, R) => { const a = deg * Math.PI / 180; return [ax + R * Math.cos(a), ay - R * Math.sin(a)]; };
    // the reticle up and to the right of Attack, the four keys hugging its left side (34 degrees apart)
    const [tx, ty] = at(70, 90);
    const tgt = $('.target'); tgt.style.left = tx + 'px'; tgt.style.top = ty + 'px';
    const ANG = [104, 138, 172, 206];
    keys.forEach((k, i) => { const [x, y] = at(ANG[i], 86); k.style.left = x + 'px'; k.style.top = y + 'px'; });
    const d = $('.dots');
    d.style.left = tx + 'px'; d.style.top = (ty - 23 - 14) + 'px';
    const j = $('.jump');
    j.style.left = ax + 'px'; j.style.top = (H - SAFE.b - 18) + 'px';
    const st = $('.strip');
    st.style.left = (W / 2) + 'px'; st.style.top = (H - SAFE.b - 22 - 40) + 'px';
    const tr = $('.tray');
    tr.style.right = (SAFE.r + 10) + 'px'; tr.style.top = (SAFE.t + 10) + 'px';
  }
  // safe-area insets as numbers (env() only works in CSS)
  const sa = document.createElement('style');
  sa.textContent = ':root{--ow-sl:env(safe-area-inset-left,0px);--ow-sr:env(safe-area-inset-right,0px);--ow-st:env(safe-area-inset-top,0px);--ow-sb:env(safe-area-inset-bottom,0px)}';
  document.head.append(sa);
  addEventListener('resize', () => { layout(); if (status.inworld) applyGameLayout(); });

  // ---- the stick --------------------------------------------------------------------------------
  // sideways on the stick strafes (camera drags turn), or turns like A/D when "Stick: turn" is set
  const HOLD = { up: 'MOVEFORWARD', down: 'MOVEBACKWARD', left: 'STRAFELEFT', right: 'STRAFERIGHT' };
  const setStickMode = (turn) => { HOLD.left = turn ? 'TURNLEFT' : 'STRAFELEFT'; HOLD.right = turn ? 'TURNRIGHT' : 'STRAFERIGHT'; };
  setStickMode(LS('ow:scheme') === 'simple');
  const held = new Set();
  function setHolds(want) {
    for (const k of Object.keys(HOLD)) {
      const on = want.has(k);
      if (on && !held.has(k)) { wenilla.hold(HOLD[k], true); held.add(k); }
      if (!on && held.has(k)) { wenilla.hold(HOLD[k], false); held.delete(k); }
    }
  }
  let stickId = null, sx = 0, sy = 0, lastStickTap = 0, stickT0 = 0, stickFar = 0;
  const RANGE = 60, DEAD = 0.22;
  function stickMove(x, y) {
    let dx = x - sx, dy = y - sy;
    const d = Math.hypot(dx, dy);
    stickFar = Math.max(stickFar, d);
    if (d > RANGE) { dx *= RANGE / d; dy *= RANGE / d; }
    knob.style.transform = `translate(${dx}px, ${dy}px)`;
    const want = new Set();
    if (d / RANGE > DEAD) {
      const a = Math.atan2(-dy, dx) * 180 / Math.PI;   // 0 = right, 90 = up
      if (a > 22.5 && a < 157.5) want.add('up');
      if (a < -22.5 && a > -157.5) want.add('down');
      if (a > 112.5 || a < -112.5) want.add('left');
      if (a < 67.5 && a > -67.5) want.add('right');
    }
    setHolds(want);
  }
  const sz = $('.stick-zone');
  sz.addEventListener('pointerdown', (e) => {
    if (winRects.some(([l, t, r, b]) => e.clientX >= l && e.clientX <= r && e.clientY >= t && e.clientY <= b)) {
      $('.world').dispatchEvent(new PointerEvent('pointerdown', e));
      return;
    }
    if (stickId !== null) return;
    stickId = e.pointerId;
    sz.setPointerCapture(e.pointerId);
    stickT0 = performance.now();
    stickFar = 0;
    sx = e.clientX; sy = e.clientY;
    stick.classList.add('live');
    stick.style.left = sx + 'px'; stick.style.top = sy + 'px';
    stickMove(sx, sy);
    status.presses += 1;
  });
  sz.addEventListener('pointermove', (e) => { if (e.pointerId === stickId) stickMove(e.clientX, e.clientY); });
  const stickEnd = (e) => {
    if (e.pointerId !== stickId) return;
    stickId = null;
    setHolds(new Set());
    // two quick taps without moving = auto-run on / off
    const now = performance.now();
    if (now - stickT0 < 220 && stickFar < 10) {
      if (now - lastStickTap < 380) { wenilla.fire('TOGGLEAUTORUN'); toast('Auto-run'); buzz(); lastStickTap = 0; } else lastStickTap = now;
    } else lastStickTap = 0;
    knob.style.transform = '';
    stick.classList.remove('live');
    stick.style.left = stick.dataset.hx + 'px'; stick.style.top = stick.dataset.hy + 'px';
  };
  sz.addEventListener('pointerup', stickEnd);
  sz.addEventListener('pointercancel', stickEnd);

  // ---- buttons ----------------------------------------------------------------------------------
  // a hold of half a second on an element (no travel): fn runs once, while the finger is still down
  function longPress(el, fn, ms = 500) {
    let t = 0, x = 0, y = 0;
    el.addEventListener('pointerdown', (e) => { x = e.clientX; y = e.clientY; clearTimeout(t); t = setTimeout(() => { t = 0; buzz(); fn(e); }, ms); });
    el.addEventListener('pointermove', (e) => { if (t && Math.hypot(e.clientX - x, e.clientY - y) > 14) { clearTimeout(t); t = 0; } });
    const stop = () => { clearTimeout(t); t = 0; };
    el.addEventListener('pointerup', stop);
    el.addEventListener('pointercancel', stop);
  }
  function press(el, fn) {
    el.addEventListener('pointerdown', (e) => {
      e.preventDefault();
      el.setPointerCapture?.(e.pointerId);
      el.classList.add('pressed');
      buzz();
      status.presses += 1;
      try { fn(e); } catch { status.errors += 1; }
    });
    const up = () => el.classList.remove('pressed');
    el.addEventListener('pointerup', up);
    el.addEventListener('pointercancel', up);
  }
  press($('.target'), () => wenilla.fire('TARGETNEARESTENEMY'));
  longPress($('.target'), () => { lua('ClearTarget()'); toast('Target cleared', 1200); });
  let targetState = { exists: false, hostile: false, dead: false };
  let role = '';
  const setRole = (r) => {
    r = ROLE_ICON[r] ? r : 'fight';
    if (r === role) return;
    role = r;
    const ico = attack.querySelector('.ico');
    ico.innerHTML = ROLE_ICON[r];
    ico.className = 'ico ' + (ROLE_TEX[r]?.includes('Gossip') ? 'gossip' : 'cursor') + (r === 'inprogress' ? ' dim' : '') + (r !== 'fight' ? ' tip' : '');
    if (ROLE_TEX[r]) iconUrl(ROLE_TEX[r]).then((u) => { if (u && role === r) ico.innerHTML = `<img alt="" src="${u}">`; });
    attack.setAttribute('aria-label', r === 'fight' ? 'Attack' : ROLE_SAY[r] || 'Interact');
  };
  press(attack, () => {
    if (!targetState.exists) { wenilla.fire('TARGETNEARESTENEMY'); return; }
    if (targetState.hostile && !targetState.dead) { wenilla.fire('ATTACKTARGET'); return; }
    toast(ROLE_SAY[role] || 'Double-tap them to talk, trade or shop');
  });

  // ability keys: four per page, page 0 = action buttons 1-4, 1 = 5-8, 2 = 9-12. A key fires when
  // the thumb lifts without travelling; a sideways swipe across the keys turns the page instead.
  let page = 0;
  const slotOf = (i) => page * 4 + i + 1;
  const setPage = (p) => {
    page = (p + 3) % 3;
    dots.forEach((d, i) => d.classList.toggle('on', i === page));
    refreshActions(true);
    toast('Actions ' + (page * 4 + 1) + '–' + (page * 4 + 4), 1000);
  };
  keys.forEach((k, i) => {
    let down = null;
    k.addEventListener('pointerdown', (e) => {
      e.preventDefault();
      k.setPointerCapture?.(e.pointerId);
      down = { x: e.clientX, y: e.clientY, id: e.pointerId, held: false };
      k.classList.add('pressed');
      const me = down;
      setTimeout(() => { if (down === me && !me.moved) { me.held = true; buzz(); keyInfo(i); } }, 480);
    });
    k.addEventListener('pointermove', (e) => { if (down && e.pointerId === down.id && Math.hypot(e.clientX - down.x, e.clientY - down.y) > 14) down.moved = true; });
    const end = (e) => {
      if (!down || e.pointerId !== down.id) return;
      k.classList.remove('pressed');
      const dx = e.clientX - down.x, dy = e.clientY - down.y;
      const held = down.held;
      down = null;
      if (e.type !== 'pointerup' || held) return;
      if (Math.abs(dx) > 34 && Math.abs(dx) > Math.abs(dy)) { setPage(page + (dx < 0 ? 1 : -1)); buzz(); return; }
      if (Math.hypot(dx, dy) > 24) return;
      buzz();
      status.presses += 1;
      // something on the cursor (a spell dragged out of the spellbook, an item, a moved action):
      // the tap puts it on this key, the way dropping it on an action button does
      if (moving) {
        // a key picked up with Move: swap it with whatever is here (the old one goes where it came from)
        const from = moving; moving = null;
        lua(`${SLOT_FN}\nPlaceAction(slot(${slotOf(i)})) PlaceAction(slot(${from})) ClearCursor()`).then(() => refreshActions(true));
        toast('Moved', 900);
        return;
      }
      if (extras.cursor) {
        lua(`${SLOT_FN}\nPlaceAction(slot(${slotOf(i)})) ClearCursor()`).then(() => refreshActions(true));
        toast('Placed', 900); extras.cursor = false;
        return;
      }
      wenilla.fire('ACTIONBUTTON' + slotOf(i));
    };
    k.addEventListener('pointerup', end);
    k.addEventListener('pointercancel', end);
  });
  press($('.dots'), () => setPage(page + 1));

  // the info card: what is on a key (the game's own tooltip text), with Move and Remove
  const info = $('.info');
  const card = (text, buttons) => {
    const t = info.querySelector('.t'), b = info.querySelector('.b');
    t.innerHTML = text;
    b.replaceChildren(...buttons.map(([label, fn]) => {
      const el = document.createElement('button');
      el.textContent = label;
      el.addEventListener('click', () => { info.classList.remove('on'); fn?.(); });
      return el;
    }));
    info.classList.add('on', 'fresh');
    setTimeout(() => info.classList.remove('fresh'), 450);   // the lifting finger's click must not land on a button
  };
  const TIP_LUA = (n) => `${SLOT_FN}
local s = slot(${n})
if not HasAction(s) then return "" end
GameTooltip:SetOwner(UIParent, "ANCHOR_NONE")
GameTooltip:SetAction(s)
local t = {}
for i = 1, GameTooltip:NumLines() do
  local l, r = getglobal("GameTooltipTextLeft" .. i), getglobal("GameTooltipTextRight" .. i)
  local a = l and l:GetText() or ""
  local b = (r and r:IsShown() and r:GetText()) or ""
  if a ~= "" or b ~= "" then table.insert(t, a .. (b ~= "" and ("   " .. b) or "")) end
end
GameTooltip:Hide()
return table.concat(t, "\\n")`;
  async function keyInfo(i) {
    const n = slotOf(i);
    const r = await lua(TIP_LUA(n));
    const text = String(r?.[0] || '');
    if (!text) {
      card('<b>Empty slot</b>\nOpen the Spellbook (or your bags), drag a spell or item out, then tap this key to put it here.',
        [['Open Spellbook', () => wenilla.fire('TOGGLESPELLBOOK')], ['Close']]);
      return;
    }
    const [title, ...rest] = text.split('\n');
    card(`<b>${esc(title)}</b>\n${esc(rest.join('\n'))}`, [
      ['Move', () => { lua(`${SLOT_FN}\nPickupAction(slot(${n}))`).then(() => refreshActions(true)); moving = n; toast('Now tap the key to move it to (swipe for other pages)', 3500); }],
      ['Remove', () => { lua(`${SLOT_FN}\nPickupAction(slot(${n})) ClearCursor()`).then(() => refreshActions(true)); toast('Removed', 900); }],
      ['Close'],
    ]);
  }

  // drawer and sheets
  const sheets = { chat: $('.sheet.chat'), menu: $('.sheet.menu'), controls: $('.sheet.controls') };
  const openSheet = (name) => {
    for (const [n, el] of Object.entries(sheets)) el.classList.toggle('open', n === name && !el.classList.contains('open'));
    root.classList.toggle('sheet-open', Object.values(sheets).some((el) => el.classList.contains('open')));
    if (name === 'chat' && sheets.chat.classList.contains('open')) { $$('.badge').forEach((b) => b.classList.remove('on')); setTimeout(() => sheets.chat.querySelector('input').focus(), 50); }
    if (name === 'menu') loadMenuIcons();
  };
  // the tray: one corner button; open, the four buttons slide out along the top edge, folding away after use
  const tray = $('.tray'), handle = $('.tray .handle');
  let trayTimer = 0;
  const setTray = (open) => {
    tray.classList.toggle('open', open);
    handle.querySelector('.hico').innerHTML = open ? ICON.close : ICON.tray;
    clearTimeout(trayTimer);
    if (open) trayTimer = setTimeout(() => setTray(false), 5000);
  };
  press(handle, () => setTray(!tray.classList.contains('open')));
  $$('.tray .item').forEach((b) => press(b, () => {
    const a = b.dataset.act;
    setTray(false);
    if (a === 'bags') wenilla.fire('OPENALLBAGS');
    else if (a === 'quests') wenilla.fire('TOGGLEQUESTLOG');
    else openSheet(a);
  }));
  $$('.sheet .x').forEach((x) => x.addEventListener('click', () => openSheet(null)));
  let menuIcons = false;
  function loadMenuIcons() {
    if (menuIcons) return;
    menuIcons = true;
    $$('.grid button').forEach((b) => iconUrl(MENU[+b.dataset.m].icon).then((u) => { if (u) b.querySelector('img').src = u; }));
  }
  $$('.grid button').forEach((b) => b.addEventListener('click', () => {
    const m = MENU[+b.dataset.m];
    if (m.cmd) wenilla.fire(m.cmd); else if (m.chat) wenilla.chat(m.chat);
    openSheet(null);
  }));
  // settings: stick strafe/turn, auto loot, interface size
  const sLabel = () => {
    root.querySelector('[data-s="loot"]').textContent = 'Auto loot: ' + (LS('ow:autoloot') === 'off' ? 'off' : 'on');
  };
  sLabel();
  // control schemes: Classic (strafe; drag turns you), Simple (stick turns; drag only looks),
  // Keyboard & mouse (touch off, the stock interface back, a corner button to return)
  const scheme = () => LS('ow:scheme') || 'classic';
  const markScheme = () => $$('.opt').forEach((o) => o.classList.toggle('sel', o.dataset.scheme === scheme()));
  function applyScheme(sc, announce) {
    LS('ow:scheme', sc);
    setStickMode(sc === 'simple');
    markScheme();
    if (sc === 'pc') {
      openSheet(null);
      turnOff();
      root.classList.add('pcmode');
      if (announce) toast('Keyboard & mouse: tap the phone button in the corner for touch controls again', 4500);
      return;
    }
    if (root.classList.contains('pcmode')) { root.classList.remove('pcmode'); turnOn(); }
    if (announce) toast(sc === 'simple' ? 'Simple: the stick turns you, dragging only looks around' : 'Classic: the stick strafes, dragging turns you', 2800);
  }
  root.querySelector('[data-s="controls"]').addEventListener('click', () => { markScheme(); openSheet('controls'); });
  $$('.opt').forEach((o) => o.addEventListener('click', () => applyScheme(o.dataset.scheme, true)));
  press($('.restore'), () => applyScheme('classic', true));
  root.querySelector('[data-s="loot"]').addEventListener('click', () => { LS('ow:autoloot', LS('ow:autoloot') === 'off' ? 'on' : 'off'); sLabel(); });
  const uiStep = (d) => {
    const f = Math.min(1.4, Math.max(0.7, Math.round(((+(LS('ow:touch-ui') || 1)) + d) * 10) / 10));
    LS('ow:touch-ui', String(f));
    if (status.inworld) applyGameLayout();
    toast('Interface size ' + Math.round(f * 100) + '%', 1200);
  };
  root.querySelector('[data-s="smaller"]').addEventListener('click', () => uiStep(-0.1));
  root.querySelector('[data-s="bigger"]').addEventListener('click', () => uiStep(0.1));

  // auto loot: the loot window empties itself (bind-on-pickup still asks)
  wenilla.on?.('LOOT_OPENED', () => {
    if (!status.inworld || LS('ow:autoloot') === 'off') return;
    lua('for i = GetNumLootItems(), 1, -1 do LootSlot(i) end');
  });

  // Close: shown while any window is open (the Escape key's job)
  press($('.closer'), () => { lua('CloseAllWindows() if CloseAllBags then CloseAllBags() end'); $('.closer').classList.remove('on'); });

  // typing into the game's own text boxes (mail, auction search, names, guild notes…): when one
  // has the keyboard focus a text bar appears; tapping it brings up the phone's keyboard, and what
  // is typed is mirrored into the box; Enter presses the box's Enter
  const typebar = $('.typebar'), tin = typebar.querySelector('input');
  let typing = '';
  const luaStr = (t) => '[==[' + String(t).replace(/\]==\]/g, '') + ']==]';
  tin.addEventListener('input', () => { if (typing) lua(`local f = ${FOCUS} if f then f:SetText(${luaStr(tin.value)}) end`); });
  typebar.addEventListener('submit', (e) => {
    e.preventDefault();
    if (!typing) return;
    lua(`local f = ${FOCUS} if f then f:SetText(${luaStr(tin.value)}) local h = f:GetScript("OnEnterPressed") if h then local old = this this = f h() this = old end end`);
    tin.blur();
  });
  typebar.querySelector('.tb-x').addEventListener('click', () => {
    if (typing) lua(`local f = ${FOCUS} if f then local h = f:GetScript("OnEscapePressed") if h then local old = this this = f h() this = old else f:ClearFocus() end end`);
    tin.blur(); typebar.classList.remove('on'); typing = '';
  });
  function focusChanged(name, text) {
    if (name === 'ChatFrameEditBox') { lua('ChatFrameEditBox:ClearFocus() ChatFrameEditBox:Hide()'); openSheet('chat'); return; }
    if (name === typing) return;
    typing = name;
    typebar.classList.toggle('on', !!name);
    if (name) { tin.value = text || ''; tin.placeholder = 'Tap here to type'; } else tin.blur();
  }

  // stances / forms and the pet bar, as a short row along the bottom edge
  const strip = $('.strip');
  let stripKey = '';
  function renderStrip(ss, pet) {
    const key = ss + '#' + pet;
    if (key === stripKey) return;
    const sameShape = stripKey.split('#')[0].split(';').map((x) => x.split('~')[0]).join() === ss.split(';').map((x) => x.split('~')[0]).join()
      && stripKey.split('#')[1]?.split(';').map((x) => x.split('~').slice(0, 2).join()).join() === pet.split(';').map((x) => x.split('~').slice(0, 2).join()).join();
    stripKey = key;
    const items = [];
    ss.split(';').filter(Boolean).forEach((x, i) => { const [tex, act, ok] = x.split('~'); items.push({ kind: 's', n: i + 1, tex, act: act === '1', off: ok !== '1' }); });
    const pets = pet.split(';').filter(Boolean).map((x) => { const [n, tex, act, auto] = x.split('~'); return { kind: 'p', n: +n, tex, act: act === '1', auto: auto === '1' }; });
    if (items.length && pets.length) items.push({ kind: 'gap' });
    items.push(...pets);
    if (!sameShape) {
      strip.replaceChildren(...items.map((it) => {
        const el = document.createElement('div');
        if (it.kind === 'gap') { el.className = 'gap'; return el; }
        el.className = 'ctl sbtn';
        el.innerHTML = '<div class="face"></div><div class="ring"></div>';
        el.dataset.kind = it.kind; el.dataset.n = it.n;
        if (it.tex) iconUrl(it.tex).then((u) => { if (u) el.querySelector('.face').style.backgroundImage = `url(${u})`; });
        press(el, () => lua(it.kind === 's' ? `CastShapeshiftForm(${it.n})` : `CastPetAction(${it.n})`));
        if (it.kind === 'p') longPress(el, () => { lua(`TogglePetAutocast(${it.n})`); toast('Autocast toggled', 1000); });
        return el;
      }));
    }
    const els = [...strip.querySelectorAll('.sbtn')];
    items.filter((it) => it.kind !== 'gap').forEach((it, i) => {
      const el = els[i];
      if (!el) return;
      el.classList.toggle('active', it.act);
      el.classList.toggle('auto', !!it.auto);
      el.classList.toggle('off', !!it.off);
    });
    layout();
  }

  // the character-creation name (and any glue-screen text box): the keyboard button relays typed
  // keys to the game the way a hardware keyboard would
  const ghost = $('.ghost');
  const keyTo = (key, code) => {
    const c = gameCanvas();
    if (!c) return;
    for (const type of ['keydown', 'keypress', 'keyup']) {
      if (type === 'keypress' && key.length !== 1) continue;
      c.dispatchEvent(new KeyboardEvent(type, { key, code, bubbles: true, cancelable: true }));
    }
  };
  press($('.kbd'), () => { ghost.value = ''; ghost.focus(); });
  ghost.addEventListener('beforeinput', (e) => {
    e.preventDefault();
    if (e.inputType === 'deleteContentBackward') keyTo('Backspace', 'Backspace');
    else if (e.inputType === 'insertLineBreak' || e.inputType === 'insertParagraph') keyTo('Enter', 'Enter');
    else if (e.data) for (const ch of e.data) keyTo(ch, /[a-z]/i.test(ch) ? 'Key' + ch.toUpperCase() : /\d/.test(ch) ? 'Digit' + ch : ch === ' ' ? 'Space' : '');
  });
  ghost.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === 'Backspace') { e.preventDefault(); keyTo(e.key, e.key); } });

  root.querySelector('[data-x="full"]').addEventListener('click', () => { fullscreen(); openSheet(null); });
  root.querySelector('[data-x="site"]').addEventListener('click', () => { openSheet(null); document.getElementById('ow-dock-handle')?.click(); });
  root.querySelector('[data-x="off"]').addEventListener('click', () => applyScheme('pc', true));

  // chat: the game's chat lines, and a box that sends like the chat box (/commands too)
  const log = $('.log');
  const COLORS = { SAY: '#fff', YELL: '#ff4040', WHISPER: '#ff80ff', PARTY: '#aaaaff', GUILD: '#40ff40', OFFICER: '#40c040', RAID: '#ff7f00', CHANNEL: '#ffc0c0', SYSTEM: '#ffff00', EMOTE: '#ff8040', MONSTER_SAY: '#ffffa0' };
  const clean = (s) => String(s || '').replace(/\|c[0-9a-fA-F]{8}/g, '').replace(/\|r/g, '').replace(/\|H[^|]*\|h(\[[^\]]*\])\|h/g, '$1');
  wenilla.on?.('chat', (p) => {
    try {
      const kind = String(p?.kind || '').toUpperCase();
      const who = p?.sender ? `[${clean(p.sender)}]: ` : '';
      const ch = p?.channel ? `[${clean(p.channel)}] ` : '';
      const line = document.createElement('div');
      line.style.color = COLORS[kind] || COLORS[kind.split('_')[0]] || '#e8dcc0';
      line.innerHTML = esc(ch + who + clean(p?.text));
      log.append(line);
      while (log.children.length > 80) log.firstChild.remove();
      log.scrollTop = log.scrollHeight;
      // the chat frames are hidden: anything addressed to you lights the tray, whispers pop up
      if (!sheets.chat.classList.contains('open') && /^(WHISPER|PARTY|PARTY_LEADER|RAID|RAID_LEADER|RAID_WARNING|GUILD|OFFICER)$/.test(kind)) {
        $$('.badge').forEach((b) => b.classList.add('on'));
        if (kind === 'WHISPER') toast(`${clean(p.sender)} whispers: ${clean(p.text)}`.slice(0, 140), 4500);
      }
    } catch { /* one bad line */ }
  });
  sheets.chat.querySelector('form').addEventListener('submit', (e) => {
    e.preventDefault();
    const inp = sheets.chat.querySelector('input');
    const text = inp.value.trim();
    if (text) wenilla.chat(text);
    inp.value = '';
  });

  // ---- character / realm screens: a finger works the glue screens like a mouse --------------------
  // Raw touches on the canvas don't register as clicks on these screens, so they are caught here and
  // replayed as mouse input through mouse(). On a phone the glue buttons are about 10 px tall, smaller
  // than a fingertip (and a finger's contact point lands a few px off where its owner aims), so:
  //   * snap: the red glue buttons (Enter World, Create New Character, Accept, Back, Delete, AddOns,
  //     Change Realm, Randomize...) are found on screen by their painted face, read back from the
  //     game's canvas; a tap anywhere near one clicks its exact centre;
  //   * aim: touch and hold shows a loupe above the finger, magnifying what is under it round a
  //     crosshair; slide onto anything (race and class icons, the little arrows, a name in the list)
  //     and lift to click it;
  //   * a quick swipe still drags (sliders, the character list, turning the model);
  //   * every click flashes a small ring where it went (green: snapped to a button).
  // ?touchdebug=1 adds a line of numbers (pixel ratio, buffer size, factor, buttons found, last tap).
  const glue = $('.glue'), loupe = $('.loupe'), ring = $('.tapring'), tdebug = $('.tdebug');
  const lctx = loupe.querySelector('canvas').getContext('2d');
  const lbuf = document.createElement('canvas');   // drawn here first: a blank read never wipes the loupe
  lbuf.width = lbuf.height = 264;
  const lbx = lbuf.getContext('2d', { willReadFrequently: true });
  if (/[?&]touchdebug=1/.test(location.search)) root.classList.add('debug');
  let targets = [], targetsAt = 0, glueLast = '';
  const rb = document.createElement('canvas');
  const rbx = rb.getContext('2d', { willReadFrequently: true });
  // read inside an animation frame (the only time the game's canvas can be read back), every 0.8 s
  // while a glue screen is up and at each touch
  let scanQueued = false;
  const scanSoon = () => new Promise((done) => {
    if (scanQueued) { setTimeout(done, 40); return; }
    scanQueued = true;
    requestAnimationFrame(() => { scanQueued = false; findButtons(); done(); });
  });
  setInterval(() => { if (status.on && root.classList.contains('glue-touch') && !document.hidden) scanSoon(); }, 800);
  function findButtons() {
    const c = gameCanvas();
    targetsAt = performance.now();
    if (!c || !c.width || !c.clientWidth) { targets = []; return; }
    try {
      const W = c.width, H = c.height, k = W > 1400 ? 0.5 : 1;   // half resolution on big buffers: plenty, 4x cheaper
      const w = Math.round(W * k), h = Math.round(H * k);
      if (rb.width !== w || rb.height !== h) { rb.width = w; rb.height = h; }
      rbx.drawImage(c, 0, 0, w, h);
      const d = rbx.getImageData(0, 0, w, h).data, n = w * h;
      // a WebGPU canvas reads back blank outside the frame it was drawn in: keep what we had
      let lit = 0;
      for (let i = 0; i < d.length && !lit; i += 4096) lit = d[i] | d[i + 1] | d[i + 2];
      if (!lit) return;
      const on = new Uint8Array(n);
      for (let i = 0, p = 0; p < n; p++, i += 4) {
        const r = d[i], g = d[i + 1], b = d[i + 2];
        if (r >= 45 && r <= 170 && g < r * 0.55 && b < r * 0.55 && Math.abs(g - b) < 30) on[p] = 1;   // the buttons' dark red
      }
      const seen = new Uint8Array(n), stack = [], found = [];
      const box = c.getBoundingClientRect(), sx = c.clientWidth / W / k, sy = c.clientHeight / H / k;
      for (let p = 0; p < n; p++) {
        if (!on[p] || seen[p]) continue;
        let x0 = w, y0 = h, x1 = -1, y1 = -1, cnt = 0;
        seen[p] = 1; stack.push(p);
        while (stack.length) {
          const q = stack.pop(), x = q % w, y = (q - x) / w;
          cnt++;
          if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y;
          if (x > 0 && on[q - 1] && !seen[q - 1]) { seen[q - 1] = 1; stack.push(q - 1); }
          if (x < w - 1 && on[q + 1] && !seen[q + 1]) { seen[q + 1] = 1; stack.push(q + 1); }
          if (y > 0 && on[q - w] && !seen[q - w]) { seen[q - w] = 1; stack.push(q - w); }
          if (y < h - 1 && on[q + w] && !seen[q + w]) { seen[q + w] = 1; stack.push(q + w); }
        }
        const tall = (y1 - y0 + 1) * sy;
        if (cnt >= 4 && tall >= 3 && tall <= 48) found.push({ x0, y0, x1, y1, cnt });
      }
      if (found.length > 300) { found.sort((p, q) => q.cnt - p.cnt); found.length = 300; }   // a red-heavy scene: the biggest pieces
      // on a small screen a button's lettering cuts its red face into pieces: join pieces that sit
      // side by side on the same line
      for (let joined = true; joined;) {
        joined = false;
        for (let i = 0; i < found.length && !joined; i++) {
          for (let j = i + 1; j < found.length; j++) {
            const a = found[i], b = found[j];
            const ha = a.y1 - a.y0 + 1, hb = b.y1 - b.y0 + 1, lo = Math.min(ha, hb);
            const overlap = Math.min(a.y1, b.y1) - Math.max(a.y0, b.y0) + 1;
            const gap = Math.max(a.x0, b.x0) - Math.min(a.x1, b.x1) - 1;
            const hi = Math.max(ha, hb), stubs = Math.min(a.x1 - a.x0, b.x1 - b.x0) + 1 < 4 * hi;
            // close pieces join; short stubs (a small button's two ends round its word) join across more
            if (overlap >= lo * 0.6 && gap <= (stubs ? Math.max(6, 2.6 * hi) : Math.max(4, 1.2 * hi))) {
              found[i] = { x0: Math.min(a.x0, b.x0), y0: Math.min(a.y0, b.y0), x1: Math.max(a.x1, b.x1), y1: Math.max(a.y1, b.y1), cnt: a.cnt + b.cnt };
              found.splice(j, 1);
              joined = true;
              break;
            }
          }
        }
      }
      // a glue button: wide, flat and mostly that red (the character's red clothes are none of these)
      targets = found.filter((t) => {
        const bw = t.x1 - t.x0 + 1, bh = t.y1 - t.y0 + 1;
        return bh * sy >= 4 && bw * sx >= 30 && bw >= bh * 2.5 && t.cnt >= bw * bh * 0.35;
      }).map((t) => ({ x: box.left + t.x0 * sx, y: box.top + t.y0 * sy, w: (t.x1 - t.x0 + 1) * sx, h: (t.y1 - t.y0 + 1) * sy }));
    } catch { targets = []; }   // a canvas that can't be read back: plain taps, no snapping
  }
  // the button a point means: inside one, or within a finger's width of its edge (nearest wins)
  function snap(x, y) {
    let best = null, bd = Infinity;
    for (const t of targets) {
      // fingers land low more than sideways: a deep zone above and below, a narrow one at the ends
      const padY = Math.max(16, t.h * 1.4), padX = 10;
      const dx = Math.max(t.x - x, 0, x - (t.x + t.w)), dy = Math.max(t.y - y, 0, y - (t.y + t.h));
      if (dx > padX || dy > padY) continue;
      const dd = Math.hypot(dx, dy * 1.4);
      if (dd < bd) { bd = dd; best = t; }
    }
    return best;
  }
  function flash(x, y, snapped) {
    ring.style.left = x + 'px'; ring.style.top = y + 'px';
    ring.classList.toggle('snap', snapped);
    ring.classList.remove('go'); void ring.offsetWidth; ring.classList.add('go');
  }
  function debugLine(extra) {
    if (!root.classList.contains('debug')) return;
    const c = gameCanvas(), [fx, fy] = pointerFactor(c);
    tdebug.textContent = `touch ${TOUCH_BUILD} · ${wenilla.state?.session?.state || '?'}${document.fullscreenElement ? ' · full screen' : ''}\n` +
      `dpr ${devicePixelRatio} buffer ${c?.width}x${c?.height} css ${c?.clientWidth}x${c?.clientHeight}\n` +
      `factor ${fx.toFixed(2)},${fy.toFixed(2)} buttons ${targets.length} taps ${status.taps} mode ${TAPMODE}${'onpointerrawupdate' in window ? ' raw' : ''}\n` +
      `${extra || glueLast}\ngame took:${tapTrace.last || ' -'}  errors ${tapTrace.errors}${tapTrace.error ? ': ' + tapTrace.error : ''}`;
  }
  async function glueTap(x, y, rescan) {
    if (rescan) await scanSoon();                      // the page changed size: find the buttons where they are now
    const t = snap(x, y);
    const px = t ? t.x + t.w / 2 : x, py = t ? t.y + t.h / 2 : y;
    click(px, py, 0);
    flash(px, py, !!t);
    status.taps += 1;
    glueLast = `tap ${Math.round(x)},${Math.round(y)} -> ${Math.round(px)},${Math.round(py)}${t ? ' snapped' : ''}`;
    debugLine();
  }
  // the loupe: 2.5x of the game round the aim point, crosshair, the button it would snap to outlined
  const ZOOM = 2.5, LR = 66;
  let aimRaf = 0;
  function drawLoupe() {
    aimRaf = 0;
    if (!gl || gl.mode !== 'aim') return;
    const c = gameCanvas();
    const x = gl.x, y = gl.y;
    let ly = y - LR - 84;
    if (ly < 4) ly = y + 52;
    loupe.style.left = Math.min(innerWidth - 2 * LR - 4, Math.max(4, x - LR)) + 'px';
    loupe.style.top = ly + 'px';
    try {
      const box = c.getBoundingClientRect(), kx = c.width / c.clientWidth, ky = c.height / c.clientHeight;
      const half = LR / ZOOM;
      lbx.fillStyle = '#000'; lbx.fillRect(0, 0, 264, 264);
      lbx.drawImage(c, (x - box.left - half) * kx, (y - box.top - half) * ky, 2 * half * kx, 2 * half * ky, 0, 0, 264, 264);
      const px = lbx.getImageData(0, 0, 264, 264).data;
      let lit = 0;
      for (let i = 0; i < px.length && !lit; i += 1024) lit = px[i] | px[i + 1] | px[i + 2];
      if (lit) lctx.drawImage(lbuf, 0, 0);
      const t = snap(x, y), toL = (v, o) => (v - o + half) * (264 / (2 * half));
      if (t) {
        lctx.strokeStyle = '#7dff9a'; lctx.lineWidth = 4;
        lctx.strokeRect(toL(t.x, x), toL(t.y, y), t.w * 264 / (2 * half), t.h * 264 / (2 * half));
      }
      lctx.strokeStyle = 'rgba(0,0,0,.8)'; lctx.lineWidth = 5;
      lctx.beginPath(); lctx.moveTo(132, 104); lctx.lineTo(132, 160); lctx.moveTo(104, 132); lctx.lineTo(160, 132); lctx.stroke();
      lctx.strokeStyle = '#ffd76a'; lctx.lineWidth = 2;
      lctx.beginPath(); lctx.moveTo(132, 104); lctx.lineTo(132, 160); lctx.moveTo(104, 132); lctx.lineTo(160, 132); lctx.stroke();
    } catch { /* not readable: the crosshair alone */ }
    // asked for from a task, not from inside this frame: the next frame's callback then runs after
    // the game has drawn (one asked for from inside a frame runs first and reads a blank canvas)
    aimRaf = setTimeout(() => { aimRaf = requestAnimationFrame(drawLoupe); }, 0);
  }
  let gl = null, aimTimer = 0;
  glue.addEventListener('pointerdown', (e) => {
    // one finger at a time; a finger whose lift never arrived (the browser lost it) stops counting
    // after a few seconds instead of blocking every tap after it
    if (gl && gl.id !== e.pointerId && performance.now() - gl.t0 < 4000) return;
    e.preventDefault();
    try { glue.setPointerCapture(e.pointerId); } catch { /* fine */ }
    gl = { id: e.pointerId, x0: e.clientX, y0: e.clientY, x: e.clientX, y: e.clientY, t0: performance.now(), mode: 'tap', w: innerWidth, h: innerHeight };
    if (TAPMODE === 'touchid') {                       // press now, as this finger's own pointer
      const t = snap(e.clientX, e.clientY);
      gl.mode = 'held'; gl.px = t ? t.x + t.w / 2 : e.clientX; gl.py = t ? t.y + t.h / 2 : e.clientY; gl.snapped = !!t;
      tapPid = e.pointerId;
      moveTo(gl.px, gl.py);
      mouse('pointerdown', gl.px, gl.py, 0, 1);
      return;
    }
    scanSoon();
    const hx = e.clientX, hy = e.clientY;
    inTurn(() => moveTo(hx, hy));                      // hover first: buttons light up, tooltips show
    clearTimeout(aimTimer);
    aimTimer = setTimeout(() => {                      // held still: aim with the loupe
      if (!gl || gl.mode !== 'tap') return;
      gl.mode = 'aim'; loupe.classList.add('on'); buzz();
      if (!aimRaf) aimRaf = requestAnimationFrame(drawLoupe);
    }, 260);
  });
  glue.addEventListener('pointermove', (e) => {
    if (!gl || gl.id !== e.pointerId || gl.mode === 'held') return;
    gl.x = e.clientX; gl.y = e.clientY;
    if (gl.mode === 'aim') { moveTo(gl.x, gl.y); return; }
    if (gl.mode === 'tap' && Math.hypot(gl.x - gl.x0, gl.y - gl.y0) > TAP_SLOP) {
      clearTimeout(aimTimer);
      gl.mode = 'drag';                                // a swipe: sliders, the character list, turning the model
      mouse('pointerdown', gl.x0, gl.y0, 0, 1);
    }
    if (gl.mode === 'drag') moveTo(gl.x, gl.y, 1);
  });
  const glueEnd = (e) => {
    if (!gl || gl.id !== e.pointerId) return;
    clearTimeout(aimTimer);
    const g = gl;
    gl = null;
    loupe.classList.remove('on');
    if (g.mode === 'held') {                           // touchid: release while the finger is still this pointer
      mouse('pointerup', g.px, g.py, 0, 0);
      tapPid = 1;
      flash(g.px, g.py, g.snapped);
      status.taps += 1;
      glueLast = `tap ${Math.round(g.x0)},${Math.round(g.y0)} -> ${Math.round(g.px)},${Math.round(g.py)}${g.snapped ? ' snapped' : ''}`;
      debugLine();
      return;
    }
    if (g.mode === 'drag') {
      // a rolled tap that just crossed the slop: let go where it pressed, so the button it landed on clicks
      if (e.type === 'pointerup' && sloppyTap(g, g.x, g.y)) { moveTo(g.x0, g.y0, 1); mouse('pointerup', g.x0, g.y0, 0, 0); status.taps += 1; }
      else mouse('pointerup', g.x, g.y, 0, 0);
      return;
    }
    // A tap is dropped only when it can't mean what the finger touched: a turn to the other
    // orientation, or the page changing size by a lot (going full screen). Android Chrome changes
    // innerHeight by a few px when its address bar or the visual viewport moves, and a
    // pointercancel can end a plain tap there: both used to drop the tap silently, so the button
    // lit up under the finger and never clicked ("highlights, no action", 2026-10-24).
    const quickCancel = e.type === 'pointercancel' && g.mode === 'tap' && performance.now() - g.t0 < LONG_MS
      && Math.hypot(g.x - g.x0, g.y - g.y0) <= TAP_SLOP;
    const turned = (g.w > g.h) !== (innerWidth > innerHeight);
    const resized = Math.abs(innerWidth - g.w) > g.w * 0.2 || Math.abs(innerHeight - g.h) > g.h * 0.2;
    if ((e.type !== 'pointerup' && !quickCancel) || turned || resized) {
      status.dropped = (status.dropped || 0) + 1;
      glueLast = `dropped: ${e.type !== 'pointerup' && !quickCancel ? e.type : turned ? 'turned' : `resized ${g.w}x${g.h}->${innerWidth}x${innerHeight}`}`;
      debugLine();
      return;
    }
    // a small resize (address bar): the same spot of the page, scaled to its new size
    const kx = innerWidth / g.w, ky = innerHeight / g.h;
    // a tap goes where the finger landed (not where it rolled to); an aimed one where the loupe aimed
    if (g.mode === 'aim') glueTap(g.x * kx, g.y * ky); else glueTap(g.x0 * kx, g.y0 * ky, kx !== 1 || ky !== 1);
  };
  glue.addEventListener('pointerup', glueEnd);
  glue.addEventListener('pointercancel', glueEnd);
  status.findButtons = async () => { await scanSoon(); return targets; };
  if (root.classList.contains('debug')) setInterval(() => debugLine(), 1000);   // numbers from the start, not only after a tap
  const GLUE = (st) => st === 'login' || st === 'charselect' || st === 'charcreate' || /realm/i.test(st || '');
  const glueState = (st) => {
    root.classList.toggle('glue-touch', GLUE(st));
    root.classList.toggle('ingame', GLUE(st) || st === 'inworld');
  };
  glueState(wenilla.state?.session?.state);
  { const st0 = wenilla.state?.session?.state; root.classList.toggle('glue-type', st0 === 'charcreate' || st0 === 'charselect' || st0 === 'login'); }

  // ---- the world: taps, double-taps, long-press, camera drags, pinch -----------------------------
  const world = $('.world');
  // A mouse (a touch-screen PC) goes straight to the game: the world layer is for fingers and pens.
  // Its drag-to-look turned the camera from page positions while the game turned it from the mouse
  // as well, and the two fought: the view snapped around. A finger or pen brings the layer back.
  addEventListener('pointermove', (e) => { if (e.isTrusted && e.pointerType === 'mouse' && !e.buttons) root.classList.add('mouse'); }, true);
  addEventListener('pointerdown', (e) => { if (e.isTrusted && e.pointerType !== 'mouse') root.classList.remove('mouse'); }, true);
  const touches = new Map();     // pointerId -> {x0,y0,x,y,t0,kind}
  let camBtn = 2;
  let lastTap = { t: 0, x: 0, y: 0 }, pinch = null, cam = null, hoverTimer = 0, uiDrag = null;
  world.addEventListener('pointerdown', (e) => {
    world.setPointerCapture(e.pointerId);
    info.classList.remove('on');
    if (moving) { const from = moving; moving = null; lua(`${SLOT_FN}\nPlaceAction(slot(${from})) ClearCursor()`).then(() => refreshActions(true)); toast('Move cancelled', 900); }
    touches.set(e.pointerId, { x0: e.clientX, y0: e.clientY, x: e.clientX, y: e.clientY, t0: performance.now(), s0: e.timeStamp, moved: false, focus: null });
    if (touches.size === 2) {
      const [a, b] = [...touches.values()];
      pinch = { d: Math.hypot(a.x - b.x, a.y - b.y) };
      for (const o of [a, b]) if (o.pressed && !o.out) { o.out = true; pressOut(o, false); }   // a pinch is no click
      endCam();
      clearTimeout(hoverTimer);
      return;
    }
    const t = touches.get(e.pointerId);
    const id = e.pointerId;
    const moved = inTurn(() => moveTo(e.clientX, e.clientY));   // after any tap still being played out
    // the second touch of a double-tap (a right-click on lift) is never pressed in
    t.maybeDbl = performance.now() - lastTap.t < 320 && Math.hypot(e.clientX - lastTap.x, e.clientY - lastTap.y) < 36;
    // is it a game window under the finger (drag it) or the world (turn the camera)?
    // asked once the cursor is there (a tap still playing out goes first), so the answer is about this spot
    t.focusP = moved.then(() => lua('local f = GetMouseFocus() return f and f.GetName and (f:GetName() or "?") or ""')).then((r) => {
      t.focus = r?.[0] ?? '';
      pressIn(t, id);
    });
    hoverTimer = setTimeout(() => { t.long = true; moveTo(t.x, t.y); }, LONG_MS);
  });
  // A finger on a game button presses it in at once and lets it out on lift, as a mouse button
  // does: the button shows pushed while the finger is on it, and the click is the release (players'
  // reports: "not in-out pressing on a single tap", 2026-10-21). Only once the game has said a window
  // is under the finger, and never for the world, a moving finger or the second tap of a double-tap.
  const onWindow = (t) => !!t.focus && t.focus !== 'WorldFrame';
  function pressIn(t, id) {
    // a quick second tap on a window is another click (paging, +/-, Next): only in the world is it a right-click
    if (!onWindow(t) || t.moved || t.lifted || pinch || touches.get(id) !== t) return;
    inTurn(async () => {
      // the focus answer came from a game update after the move; one more and its hover is current
      await gameTicks(1);
      if (t.moved || t.lifted || pinch || touches.get(id) !== t || t.pressed) return;
      moveTo(t.x0, t.y0);
      mouse('pointerdown', t.x0, t.y0, 0, 1);
      t.pressed = performance.now();
    });
  }
  // Let a pressed button out: where it was pressed (a click), or off the screen (no click: a long
  // press is a hover, for the tooltip), then back over it so the tooltip stays.
  function pressOut(t, click) {
    return inTurn(async () => {
      await settle();                                  // never the same game update as the press
      if (click) { moveTo(t.x0, t.y0, 1); mouse('pointerup', t.x0, t.y0, 0, 0); return; }
      moveTo(-40, -40, 1); mouse('pointerup', -40, -40, 0, 0);
      await afterFrame(); moveTo(t.x0, t.y0);
    });
  }
  world.addEventListener('pointermove', (e) => {
    const t = touches.get(e.pointerId);
    if (!t) return;
    t.x = e.clientX; t.y = e.clientY;
    if (pinch && touches.size === 2) {
      const [a, b] = [...touches.values()];
      const d = Math.hypot(a.x - b.x, a.y - b.y);
      while (d - pinch.d > 28) { wenilla.fire('CAMERAZOOMIN'); pinch.d += 28; }
      while (pinch.d - d > 28) { wenilla.fire('CAMERAZOOMOUT'); pinch.d -= 28; }
      return;
    }
    if (!t.moved && Math.hypot(t.x - t.x0, t.y - t.y0) > TAP_SLOP) {
      // window or world under the finger? wait for the answer (a few ms) before choosing
      if (t.focus === null || t.focus === undefined) {
        if (!t.waiting) { t.waiting = true; t.focusP?.then(() => { if (touches.get(e.pointerId) === t && !t.moved) { startDrag(t, e.pointerId); moveTo(t.x, t.y, uiDrag === e.pointerId ? 1 : (camBtn === 2 ? 2 : 1)); } }); }
        return;
      }
      startDrag(t, e.pointerId);
    }
    if (t.moved) moveTo(t.x, t.y, uiDrag === e.pointerId ? 1 : cam === e.pointerId ? (camBtn === 2 ? 2 : 1) : 0);
  });
  function startDrag(t, id) {
    t.moved = true;
    clearTimeout(hoverTimer);
    const onUi = t.focus && t.focus !== 'WorldFrame' && t.focus !== '';
    if (onUi) { uiDrag = id; if (!t.pressed) mouse('pointerdown', t.x0, t.y0, 0, 1); }
    else { cam = id; camBtn = LS('ow:scheme') === 'simple' ? 0 : 2; mouse('pointerdown', t.x0, t.y0, camBtn, camBtn === 2 ? 2 : 1); status.drags += 1; }
  }
  function endCam() {
    if (cam !== null) { const t = touches.get(cam); if (t) mouse('pointerup', t.x, t.y, camBtn, 0); cam = null; }
    if (uiDrag !== null) {
      const t = touches.get(uiDrag);
      // a rolled tap on a window: let go where it pressed, so the button it landed on clicks
      if (t) { if (t.lifted && sloppyTap(t, t.x, t.y)) { moveTo(t.x0, t.y0, 1); mouse('pointerup', t.x0, t.y0, 0, 0); } else mouse('pointerup', t.x, t.y, 0, 0); }
      uiDrag = null;
    }
  }
  const worldEnd = (e) => {
    const t = touches.get(e.pointerId);
    if (!t) return;
    clearTimeout(hoverTimer);
    if (pinch) { touches.delete(e.pointerId); if (touches.size < 2) pinch = null; return; }
    t.lifted = e.type === 'pointerup';
    if (t.pressed && !t.out && !t.moved && cam !== e.pointerId && uiDrag !== e.pointerId) {
      // pressed in on a game button: out where it went in. A quick lift is the click; a long press
      // (the tooltip) or a cancelled touch lets go off the button.
      const quick = t.lifted && e.timeStamp - t.s0 < LONG_MS;
      pressOut(t, quick);
      if (quick) { status.taps += 1; lastTap = { t: 0, x: 0, y: 0 }; }   // a window tap never starts a double-tap
      touches.delete(e.pointerId);
      return;
    }
    if (cam === e.pointerId && t.lifted && sloppyTap(t, t.x, t.y)) {
      // a quick little swipe on the world was meant as a tap (target, loot, talk): end the turn, tap
      endCam(); click(t.x0, t.y0, 0); status.taps += 1;
    } else if (cam === e.pointerId || uiDrag === e.pointerId) endCam();
    // a tap: no drag began (or one was still waiting to hear what is under the finger)
    else if (!t.moved && e.type === 'pointerup' && e.timeStamp - t.s0 < LONG_MS && (!t.waiting || sloppyTap(t, t.x, t.y))) {
      t.x = t.x0; t.y = t.y0;                          // the tap is where the finger landed, not where it rolled to
      const now = performance.now();
      status.taps += 1;
      // a window or the world? A quick tap can lift before the game has said (a frame): wait for it,
      // so two quick taps on a window's button are two clicks, not a click and a right-click
      const decide = () => {
        const dbl = !onWindow(t) && now - lastTap.t < 320 && Math.hypot(t.x - lastTap.x, t.y - lastTap.y) < 36;
        click(t.x, t.y, dbl ? 2 : 0);
        lastTap = dbl || onWindow(t) ? { t: 0, x: 0, y: 0 } : { t: now, x: t.x, y: t.y };
      };
      if (t.focus === null || t.focus === undefined) Promise.race([t.focusP, wait(300)]).then(decide, decide);
      else decide();
    }
    touches.delete(e.pointerId);
  };
  world.addEventListener('pointerup', worldEnd);
  world.addEventListener('pointercancel', worldEnd);

  // ---- action keys: icons, cooldowns, usability, range -----------------------------------------
  const ACTION_LUA = `${SLOT_FN}
local now = GetTime()
local out = {}
for i = 1, 12 do
  local s = slot(i)
  local tex = GetActionTexture(s) or ""
  local st, du, en = GetActionCooldown(s)
  local rem = 0
  if st and du and en == 1 and du > 1.6 then rem = st + du - now end
  local u, nm = IsUsableAction(s)
  local r = IsActionInRange(s)
  local c = GetActionCount and GetActionCount(s) or 0
  table.insert(out, tex .. "|" .. string.format("%.1f", rem) .. "|" .. (u and 1 or 0) .. (nm and 1 or 0) .. "|" .. tostring(r) .. "|" .. (c or 0))
end
local ex = UnitExists("target") and 1 or 0
local ho = (UnitCanAttack and UnitCanAttack("player", "target")) and 1 or 0
local de = UnitIsDead("target") and 1 or 0
-- what Attack / Interact would do with the target
local role = "fight"
if ex == 1 and not (ho == 1 and de == 0) then
  if de == 1 then role = "loot"
  elseif UnitIsPlayer("target") then role = "player"
  else
    local nm = UnitName("target") or ""
    local T = __OWTOUCH or {}
    role = ""
    if Compass then
      for i = 1, (GetNumQuestLogEntries and GetNumQuestLogEntries() or 0) do
        local t, _, _, hdr, _, done = GetQuestLogTitle(i)
        local m = t and not hdr and Compass.meta and Compass.meta[t]
        if m and m.turnIn and m.turnIn.npc == nm then role = (done == 1) and "turnin" or "inprogress" if done == 1 then break end end
      end
      if role ~= "turnin" and Compass.nearby then
        for _, e in ipairs(Compass.nearby) do
          if e.giver == nm and not (Compass.FindQuest and Compass:FindQuest(e.title)) then role = "quest" break end
        end
      end
    end
    if role == "" then
      T.roles = T.roles or {}
      role = T.roles[nm]
      if not role then
        GameTooltip:SetOwner(UIParent, "ANCHOR_NONE")
        GameTooltip:SetUnit("target")
        local sub = string.lower((GameTooltipTextLeft2 and GameTooltipTextLeft2:GetText()) or "")
        GameTooltip:Hide()
        local function has(p) return string.find(sub, p, 1, true) end
        if has("spirit healer") then role = "spirit"
        elseif has("innkeeper") then role = "inn"
        elseif has("flight") or has("gryphon") or has("hippogryph") or has("wind rider") or has("bat handler") then role = "flight"
        elseif has("repair") or has("armor") or has("blacksmith") or has("weapon") or has("shield") or has("mail") then role = "repair"
        elseif has("trainer") then role = "train"
        elseif has("bank") then role = "bank"
        elseif has("stable") then role = "stable"
        elseif has("battlemaster") then role = "battle"
        elseif has("guild") or has("tabard") then role = "guild"
        elseif has("<") then role = "shop"
        else role = "talk" end
        if __OWTOUCH then T.roles[nm] = role end
      end
    end
  end
end
-- what else the touch layer reacts to: the box with the keyboard focus, open windows,
-- something on the cursor, stances/forms and the pet bar
local kf = ${FOCUS}
if kf and not kf:IsVisible() then kf = nil end
local kfn = kf and (kf:GetName() or "?") or ""
local kft = (kf and kf.GetText and kf:GetText()) or ""
local open = 0
for _, fn in ipairs({ "GetLeftFrame", "GetCenterFrame", "GetDoublewideFrame", "GetFullScreenFrame" }) do
  local g = getglobal(fn) if g and g() then open = 1 end
end
-- every open window's rectangle in CSS px, so a touch on a window over the stick reaches the window
local rects, seen = {}, {}
local ch = (__OWTOUCH and __OWTOUCH.cssH) or 360
local up = UIParent:GetHeight() / ch
local function rect(f)
  if not f or seen[f] or not f:IsVisible() or not f:GetLeft() then return end
  seen[f] = true
  local s = f:GetEffectiveScale() / UIParent:GetEffectiveScale()
  local l, b, w, h = f:GetLeft() * s, f:GetBottom() * s, f:GetWidth() * s, f:GetHeight() * s
  table.insert(rects, math.floor(l / up) .. "," .. math.floor((UIParent:GetHeight() - b - h) / up) .. "," .. math.ceil((l + w) / up) .. "," .. math.ceil((UIParent:GetHeight() - b) / up))
end
for _, fn in ipairs({ "GetLeftFrame", "GetCenterFrame", "GetDoublewideFrame", "GetFullScreenFrame" }) do local g = getglobal(fn) if g then rect(g()) end end
if UISpecialFrames then for _, n in ipairs(UISpecialFrames) do rect(getglobal(n)) end end
for i = 1, (NUM_CONTAINER_FRAMES or 12) do rect(getglobal("ContainerFrame" .. i)) end
for _, n in ipairs({ "StaticPopup1", "StaticPopup2", "StaticPopup3", "StaticPopup4", "LootFrame", "GroupLootFrame1", "GroupLootFrame2", "ItemRefTooltip", "DropDownList1", "DropDownList2" }) do rect(getglobal(n)) end
if table.getn(rects) > 0 then open = 1 end
local cur = ((CursorHasSpell and CursorHasSpell()) or (CursorHasItem and CursorHasItem()) or (CursorHasMacro and CursorHasMacro())) and 1 or 0
local ss = {}
for i = 1, (GetNumShapeshiftForms and GetNumShapeshiftForms() or 0) do
  local tex, nm, act, ok = GetShapeshiftFormInfo(i)
  table.insert(ss, (tex or "") .. "~" .. (act and 1 or 0) .. "~" .. (ok and 1 or 0))
end
local pet = {}
if PetHasActionBar and PetHasActionBar() then
  for i = 1, 10 do
    local nm, sub, tex, tok, act, aok, aon = GetPetActionInfo(i)
    if nm then
      if tok then tex = getglobal(tex) end
      table.insert(pet, i .. "~" .. (tex or "") .. "~" .. (act and 1 or 0) .. "~" .. (aon and 1 or 0))
    end
  end
end
return table.concat(out, "\\n"), ex, ho, de, kfn, kft, open, cur, table.concat(ss, ";"), table.concat(pet, ";"), table.concat(rects, ";"), role`;
  let actions = [];
  let actBusy = false;
  const extras = { cursor: false };
  let winRects = [];
  let moving = null;   // the action slot (1-12) a Move picked up, until a key takes it
  async function refreshActions(force) {
    if (actBusy && !force) return;
    actBusy = true;
    try {
      const r = await lua(ACTION_LUA);
      if (!r || !r[0]) return;
      actions = String(r[0]).split('\n').map((l) => {
        const [tex, rem, un, range, count] = l.split('|');
        return { tex, rem: +rem, usable: un?.[0] === '1', nomana: un?.[1] === '1', range, count: parseInt(count, 10) || 0 };
      });
      targetState = { exists: r[1] == 1, hostile: r[2] == 1, dead: r[3] == 1 };
      extras.cursor = r[7] == 1;
      $('.closer').classList.toggle('on', r[6] == 1);
      focusChanged(String(r[4] || ''), String(r[5] || ''));
      renderStrip(String(r[8] || ''), String(r[9] || ''));
      winRects = String(r[10] || '').split(';').filter(Boolean).map((x) => x.split(',').map(Number));
      root.classList.toggle('windows', winRects.length > 0);
      attack.classList.toggle('hostile', targetState.exists && targetState.hostile && !targetState.dead);
      setRole(String(r[11] || 'fight'));
      keys.forEach((k, i) => {
        const a = actions[slotOf(i) - 1];
        const face = k.querySelector('.face');
        if (!a || !a.tex) { face.style.backgroundImage = ''; face.dataset.tex = ''; face.classList.remove('icon'); k.className = 'ctl key play empty'; k.querySelector('.count').textContent = ''; return; }
        k.classList.remove('empty');
        if (face.dataset.tex !== a.tex) {
          face.dataset.tex = a.tex;
          iconUrl(a.tex).then((u) => { if (u && face.dataset.tex === a.tex) { face.style.backgroundImage = `url(${u})`; face.classList.add('icon'); } });
        }
        k.classList.toggle('cooling', a.rem > 0);
        k.querySelector('.cd').textContent = a.rem > 0 ? (a.rem >= 60 ? Math.ceil(a.rem / 60) + 'm' : Math.ceil(a.rem)) : '';
        k.classList.toggle('unusable', !a.usable && !a.nomana);
        k.classList.toggle('nomana', a.nomana);
        k.classList.toggle('far', a.range === '0');
        k.querySelector('.count').textContent = a.count > 1 ? a.count : '';
      });
    } finally { actBusy = false; }
  }

  // ---- the game's own frames, rearranged for a small screen ------------------------------------
  function gameLayoutLua(on) {
    const c = gameCanvas();
    const cssH = Math.max(200, c?.clientHeight || innerHeight);
    // interface height in game units: 560 on a phone, up to the stock 768 on a tablet
    const size = Math.min(1.4, Math.max(0.7, +(LS('ow:touch-ui') || 1)));
    const vh = Math.round(Math.min(768, Math.max(560, cssH * 1.5)) / size);
    const drawer = 10 + 36 + 8;   // the tray button's column right of the minimap
    return `local on = ${on ? 'true' : 'false'}
if not __OWTOUCH then __OWTOUCH = { hidden = {}, orig = {} } end
local T = __OWTOUCH
T.orig = T.orig or {}
local function place(name, pt, rel, x, y, s)
  local f = getglobal(name) if not f then return end
  if not T.orig[name] then
    local a, r, b, ox, oy = f:GetPoint(1)
    T.orig[name] = { a, r, b, ox, oy, f:GetScale() }
  end
  f:SetScale(s or 1) f:ClearAllPoints() f:SetPoint(pt, UIParent, rel, x / (s or 1), y / (s or 1))
end
local function hide(f) if f and f:IsShown() then f:Hide() table.insert(T.hidden, f) end end
if on then
  if not T.s0 then T.s0 = UIParent:GetScale() end
  -- the interface spans ${vh} units of height whatever the screen (idempotent: re-applying keeps it)
  local k = UIParent:GetScale() * UIParent:GetHeight() / ${vh}
  UIParent:SetScale(k)
  local u = UIParent:GetHeight() / ${cssH}
  T.cssH = ${cssH}
  -- player and target side by side along the top-left edge, one scale, one style
  place("PlayerFrame", "TOPLEFT", "TOPLEFT", 16 * u - 19, -12 * u + 4, 1)
  place("TargetFrame", "TOPLEFT", "TOPLEFT", 16 * u - 19 + 238, -12 * u + 4, 1)
  local ms = 100 * u / 140
  place("MinimapCluster", "TOPRIGHT", "TOPRIGHT", -${drawer} * u + 14 * ms, -12 * u + 10 * ms, ms)
  -- buffs: the game hangs BuffFrame off TemporaryEnchantFrame, so that is the one to move
  place("TemporaryEnchantFrame", "TOPRIGHT", "TOPRIGHT", -(${drawer} + 104) * u, -12 * u, 0.8)
  if BuffFrame then if not T.orig.BuffScale then T.orig.BuffScale = BuffFrame:GetScale() end BuffFrame:SetScale(0.8) end
  -- the quest arrow (and its distance line) at the top centre, between the frames and the minimap
  place("Compass_Arrow", "TOP", "TOP", 0, -14 * u)
  -- tutorial alert buttons: a tidy row just above the bottom edge, between stick and cluster
  local n = 0
  while getglobal("TutorialFrameAlertButton" .. (n + 1)) do n = n + 1 end
  for i = 1, n do
    place("TutorialFrameAlertButton" .. i, "BOTTOM", "BOTTOM", ((i - 1) - (n - 1) / 2) * 24 * u, 56 * u, 0.5)
  end
  -- quest tracker: under the player frame on a phone (the cluster needs the right side), under
  -- the quest arrow on a tablet
  if ${cssH} >= 480 then
    place("Compass_Tracker", "TOPRIGHT", "TOPRIGHT", -${drawer} * u, -(12 + 100 + 52) * u, 0.9)
    place("QuestWatchFrame", "TOPRIGHT", "TOPRIGHT", -${drawer} * u, -(12 + 100 + 52) * u, 0.9)
  else
    place("Compass_Tracker", "TOPLEFT", "TOPLEFT", 16 * u, -70 * u, 0.85)
    place("QuestWatchFrame", "TOPLEFT", "TOPLEFT", 16 * u, -70 * u, 0.85)
  end
  if not T.applied then
    for _, n in ipairs({ "MainMenuBar", "MultiBarBottomLeft", "MultiBarBottomRight", "MultiBarLeft", "MultiBarRight", "BonusActionBarFrame", "ShapeshiftBarFrame", "PetActionBarFrame", "MainMenuBarArtFrame", "Chronicle_Frame" }) do hide(getglobal(n)) end
    local f = EnumerateFrames()
    while f do
      local nm = f:GetName()
      if nm and f:GetParent() == UIParent and (string.find(nm, "^ChatFrame") or string.find(nm, "^CPChat") or string.find(nm, "^ChatFrame1CP")) then hide(f) end
      f = EnumerateFrames(f)
    end
    T.applied = true
  end
  return "on", k
else
  UIParent:SetScale(T.s0 or 1)
  T.s0 = nil
  if BuffFrame and T.orig.BuffScale then BuffFrame:SetScale(T.orig.BuffScale) end
  T.orig.BuffScale = nil
  for name, o in pairs(T.orig) do
    local f = getglobal(name)
    if f and o[1] then f:SetScale(o[6] or 1) f:ClearAllPoints() f:SetPoint(o[1], o[2] or UIParent, o[3] or o[1], o[4] or 0, o[5] or 0) end
  end
  T.orig = {}
  for _, f in ipairs(T.hidden) do f:Show() end
  T.hidden = {} T.applied = nil
  return "off"
end`;
  }
  let layoutBusy = false;
  async function applyGameLayout() {
    if (layoutBusy) return;
    layoutBusy = true;
    try {
      const r = await lua(gameLayoutLua(true));
      status.layout = r?.[0] || 'failed';
    } finally { layoutBusy = false; }
  }

  // ---- on / off, world entry -------------------------------------------------------------------
  let actTimer = 0, layTimer = 0, wake = null;
  const fsEl = () => document.fullscreenElement || document.webkitFullscreenElement;
  const el0 = document.documentElement;
  const canFs = !!((document.fullscreenEnabled || document.webkitFullscreenEnabled) && (el0.requestFullscreen || el0.webkitRequestFullscreen));
  // the installed app (Add to Home Screen; the manifest asks for full screen, landscape)
  const installed = () => matchMedia('(display-mode: fullscreen), (display-mode: standalone)').matches || navigator.standalone === true;
  const lockLandscape = () => { try { screen.orientation?.lock?.('landscape').catch(() => {}); } catch { /* not supported */ } };
  function fullscreen() {
    if (fsEl()) { lockLandscape(); return; }
    try {
      const p = el0.requestFullscreen ? el0.requestFullscreen({ navigationUI: 'hide' }) : el0.webkitRequestFullscreen?.();
      Promise.resolve(p).then(lockLandscape).catch(() => {});
    } catch { /* refused */ }
  }
  const phone = () => Math.min(screen.width || innerWidth, screen.height || innerHeight) < 600 || Math.min(innerWidth, innerHeight) < 500;
  let fsSkip = false;
  try { fsSkip = sessionStorage.getItem('ow:fs-skip') === '1'; } catch { /* storage blocked */ }
  function fsState() {
    root.classList.toggle('phone', phone());
    root.classList.toggle('canfs', canFs && !installed());
    root.classList.toggle('wantfs', !fsEl() && !fsSkip);
  }
  const takeTap = (el, fn) => el.addEventListener('pointerdown', (e) => { e.preventDefault(); e.stopPropagation(); fn(e); });
  takeTap($('.fsgo'), (e) => {
    if (e.target.closest('.skip')) { fsSkip = true; try { sessionStorage.setItem('ow:fs-skip', '1'); } catch { /* fine */ } fsState(); return; }
    fullscreen();
  });
  takeTap($('.rotate .go'), () => fullscreen());   // Android: full screen and turns to landscape by itself
  for (const ev of ['fullscreenchange', 'webkitfullscreenchange']) document.addEventListener(ev, () => { fsState(); layout(); });
  addEventListener('resize', fsState);
  screen.orientation?.addEventListener?.('change', () => { fsState(); if (fsEl()) lockLandscape(); });
  fsState();
  // iPhone Safari has no full screen for pages: the installed app is the way (said once per visit)
  let iosHint = false;
  const iosTip = () => {
    if (iosHint || canFs || installed() || !phone() || !/iPhone|iPod/.test(navigator.userAgent)) return;
    iosHint = true;
    setTimeout(() => toast('For full screen: tap Share, then Add to Home Screen, and play from the Open Vanilla icon', 7000), 1500);
  };

  function enterWorld() {
    document.body.classList.add('ow-touch-world');
    if (LS('ow:scheme') === 'simple') lua('if SetCVar then SetCVar("cameraSmoothStyle", "1") end');
    if (!status.on || status.inworld) return;
    status.inworld = true;
    root.classList.add('inworld');
    layout();
    setTimeout(applyGameLayout, 1200);
    setTimeout(() => lua(FOCUS_HOOK), 2500);
    clearInterval(layTimer);
    // re-apply after a /reload (a fresh interface comes back at its stock layout)
    layTimer = setInterval(async () => {
      // anything an addon showed again (its own upkeep) goes back out of the way
      const r = await lua('if __OWTOUCH and __OWTOUCH.applied then for _, f in ipairs(__OWTOUCH.hidden) do if f:IsShown() then f:Hide() end end return "yes" end return "no"');
      if (r?.[0] === 'no') applyGameLayout();
      lua(FOCUS_HOOK);
    }, 5000);
    clearInterval(actTimer);
    actTimer = setInterval(() => { if (!document.hidden) refreshActions(); }, 250);
    // warm the menu sheet's icons once the world has settled, so it opens fully drawn
    setTimeout(() => { MENU.forEach((m) => iconUrl(m.icon).catch(() => {})); Object.values(ROLE_TEX).forEach((t) => iconUrl(t).catch(() => {})); }, 8000);
    navigator.wakeLock?.request?.('screen').then((w) => { wake = w; }).catch(() => {});
    const seen = +(LS('ow:touch-hints') || 0);
    if (seen < 3) { LS('ow:touch-hints', String(seen + 1)); setTimeout(() => toast('Drag to look · Tap to target · Double-tap to talk and loot · Menu ▸ Controls to change how it plays', 6000), 2500); }
  }
  function leaveWorld() {
    document.body.classList.remove('ow-touch-world');
    status.inworld = false;
    root.classList.remove('inworld');
    clearInterval(actTimer); clearInterval(layTimer);
    setHolds(new Set());
    wake?.release?.().catch(() => {}); wake = null;
  }
  function turnOn() {
    if (status.on) return;
    status.on = true;
    root.classList.add('on');
    document.body.classList.add('ow-touch-on');
    layout();
    if (wenilla.state?.session?.state === 'inworld') enterWorld();
  }
  function turnOff() {
    if (!status.on) return;
    if (status.inworld) lua(gameLayoutLua(false));
    leaveWorld();
    status.on = false;
    root.classList.remove('on');
    document.body.classList.remove('ow-touch-on', 'ow-touch-world');
  }
  status.turnOn = () => { LS('ow:touch', 'on'); turnOn(); };
  status.turnOff = () => { LS('ow:touch', 'off'); turnOff(); };

  // hidden behind the loading screen (stages.js: 'world-loading' until 'world-ready')
  let loadSafety = 0;
  addEventListener('ow:progress', (e) => {
    if (e.detail === 'world-loading') {
      root.classList.add('loading');
      clearTimeout(loadSafety);
      loadSafety = setTimeout(() => root.classList.remove('loading'), 180000);
    } else if (e.detail === 'world-ready') {
      clearTimeout(loadSafety);
      root.classList.remove('loading');
      if (status.inworld) setTimeout(applyGameLayout, 300);
    }
  });

  wenilla.on?.('state', (s) => {
    const st = s?.state;
    if (st === 'inworld') enterWorld(); else if (status.inworld) leaveWorld();
    root.classList.toggle('glue-type', st === 'charcreate' || st === 'charselect' || st === 'login');
    glueState(st);
    if (GLUE(st)) iosTip();
  });

  // a controller takes over: the bridge's gamepad mapper, touch controls out of the way
  addEventListener('gamepadconnected', () => {
    try { wenilla.gamepad?.start?.(); } catch { /* mapper missing */ }
    if (status.on) { turnOff(); toast('Controller connected: touch controls hidden'); status.byPad = true; }
  });
  addEventListener('gamepaddisconnected', () => { if (status.byPad && wanted()) { status.byPad = false; turnOn(); } });

  if (wanted()) { if (LS('ow:scheme') === 'pc') root.classList.add('pcmode'); else turnOn(); }
  return status;
}
