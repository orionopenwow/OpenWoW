--[[ Herald (in game): let Herald play this character while you watch. Any race, any class, any zone.

Herald here is the realm's own bot AI in "self-bot" mode: ".bot self" hands your character to it
and ".bot self" again takes it back; ".bot cmd <you> nc +grind,+quest" tells it what to do. You
stay logged in and watch your own character play, with the camera, chat and the whole UI as usual.

The realm decides: self-bot only works where the server owner has set AiPlayerbot.SelfBotLevel to 2
(Open Vanilla Server and Play Solo do this; Vanilla Remastered when its owner turns it on). Where it's
off, the panel says so.

Herald Autopilot (the desktop app) can also hand the character over from outside the game: the
server then says "Enable player ai (Autopilot)" and the app chooses what he does.

/herald            show or hide the panel
/herald play|stop  hand over / take back
Written for the 1.12 client's Lua (5.0): no # operator, no string.match.
]]

HeraldDB = HeraldDB or {}

local GOALS = {
  { id = "level",   label = "Level up", tip = "Fights, quests and travels where your level fits.",
    nc = "+grind,+rpg,+rpg quest,+travel,+loot,+food,+quest" },
  { id = "quest",   label = "Quest",    tip = "Takes and finishes quests; fights only for them.",
    nc = "+rpg,+rpg quest,+quest,+travel,+loot,+food,-grind" },
  { id = "gather",  label = "Gather",   tip = "Mines and picks herbs (needs the profession).",
    nc = "+gather,+loot,+food,+travel,-rpg" },
  { id = "explore", label = "Explore",  tip = "Wanders the world and sees new places.",
    nc = "+explore,+travel,+rpg,+loot,+food,-grind" },
}

-- Always off on your own character: the bot AI's selling, auction house, mail, bank, guild, crafting,
-- battleground, duel and chatter habits (its vendor runs would sell even an epic mount), and its
-- "maintenance" (destroys, disenchants and opens items, abandons quests).
-- "-mount": he travels on foot for now (owner, 2026-10-24); "+mount" brings riding back.
local SAFE = "-rpg vendor,-rpg bank,-rpg guild,-rpg craft,-rpg bg,-rpg player,-maintenance,-guild,-pvp,-bg,-arena,-lfg,-duel,-start duel,-ads,-ai chat,-say,-emote,+silent,-mount"

-- In a fight, every goal: never run from a fight he can win. The bot AI's "flee" makes a character
-- playing alone run as soon as two mobs are on him and he has lost any health (it counts itself as
-- 100 + its health %, each same-level mob as 100), and running drags him into more mobs; potions
-- instead. "custom::herald" (realm/classicplus/classicplus_herald_ai.sql) adds the corpses round him
-- to his loot list before he picks the next fight, so he loots every kill.
local COMBAT = "-flee,+potions"
local LOOT = "+custom::herald"
-- What he picks up: the bot AI's default skips grey items; with "trash" he takes everything, as
-- the client's auto loot did before he became the only one looting (see autoLootOff below).
local LOOT_LIST = "trash"

local mod = math.mod or math.fmod

local H = { notes = {}, active = false, started = nil, xp = 0, kills = 0, deaths = 0, money = 0, lastMoney = nil,
            lastXP = nil, lastMax = nil, pendingGoal = nil, wait = 0, available = nil }

local function msg(text)
  DEFAULT_CHAT_FRAME:AddMessage("|cffe9c46a[Herald]|r " .. text)
end

local function me()
  return UnitName("player")
end

local function send(cmd)
  H.quietUntil = GetTime() + 1.5
  SendChatMessage(cmd, "SAY")
end

-- Herald doesn't talk. The bot AI's replies to his orders ("Sending command ...", "Enable player ai",
-- strategy lists), anything it whispers to its own character, and the system lines that answer an
-- order in the next 1.5 s never reach the chat window. Herald's own event frame still sees them.
local QUIET = { "^Sending command ", "Enable player ai", "Disable player ai", "^Strateg", "^Unknown strategy" }
local function botLine(e, text, author)
  if not text then return false end
  if (e == "CHAT_MSG_WHISPER" or e == "CHAT_MSG_WHISPER_INFORM") and author == UnitName("player") then return true end
  if e == "CHAT_MSG_SAY" and author == UnitName("player") and string.find(text, "^%.") then return true end
  if e ~= "CHAT_MSG_SYSTEM" then return false end
  local i
  for i = 1, table.getn(QUIET) do
    if string.find(text, QUIET[i]) then return true end
  end
  return H.quietUntil ~= nil and GetTime() < H.quietUntil
end
if ChatFrame_OnEvent then
  local origChat = ChatFrame_OnEvent
  ChatFrame_OnEvent = function(ev)
    if botLine(ev or event, arg1, arg2) then return end
    return origChat(ev)
  end
end

local function goalById(id)
  local i
  for i = 1, table.getn(GOALS) do
    if GOALS[i].id == id then return GOALS[i] end
  end
  return GOALS[1]
end

-- Herald's orders to the bot AI: what to do out of a fight (the goal), how to fight, and loot.
-- Sent again on login, level-up and every few minutes: the bot AI puts its own defaults (flee back
-- in) whenever it resets a character's strategies.
-- (Three short lines: one with everything would pass the client's 255-byte chat limit with a long name.)
-- His class rotation for his level band (realm/classicplus/classicplus_herald_rotations.sql: custom
-- strategies herald_<class>_1, _20 and _40); the other bands of his class are switched off, so a level-up
-- across a band never leaves two on.
local BANDS = { 1, 20, 40 }
local function rotation()
  local _, class = UnitClass("player")
  class = string.lower(class or "warrior")
  local lv = UnitLevel("player") or 1
  local band = 1
  if lv >= 40 then band = 40 elseif lv >= 20 then band = 20 end
  local out, i = "+custom::herald_" .. class .. "_" .. band, 1
  for i = 1, table.getn(BANDS) do
    if BANDS[i] ~= band then out = out .. ",-custom::herald_" .. class .. "_" .. BANDS[i] end
  end
  return out
end

local function orders(id, combatOnly)
  if not combatOnly then
    send(".bot cmd " .. me() .. " nc " .. goalById(id).nc .. "," .. SAFE)
  end
  -- loot and rest go with every resend, Autopilot runs too: a reset of the bot AI drops them
  send(".bot cmd " .. me() .. " nc " .. LOOT)
  send(".bot cmd " .. me() .. " ll " .. LOOT_LIST)
  send(".bot cmd " .. me() .. " co " .. COMBAT .. "," .. rotation())
end

local function money(c)
  c = math.floor(c or 0)
  local g = math.floor(c / 10000)
  local s = math.floor(mod(c, 10000) / 100)
  local k = mod(c, 100)
  if g > 0 then return g .. "|cffffd700g|r " .. s .. "|cffc7c7cfs|r" end
  if s > 0 then return s .. "|cffc7c7cfs|r " .. k .. "|cffeda55fc|r" end
  return k .. "|cffeda55fc|r"
end

local function clock(sec)
  sec = math.floor(sec or 0)
  local h = math.floor(sec / 3600)
  local m = math.floor(mod(sec, 3600) / 60)
  local s = mod(sec, 60)
  if h > 0 then return string.format("%d:%02d:%02d", h, m, s) end
  return string.format("%d:%02d", m, s)
end

-- ------------------------------------------------------------------------------------------ panel
local f = CreateFrame("Frame", "HeraldPanel", UIParent)
f:SetWidth(250); f:SetHeight(300)
f:SetPoint("TOPRIGHT", UIParent, "TOPRIGHT", -24, -190)   -- under the minimap, on screen at any width
f:SetFrameStrata("MEDIUM")
f:SetMovable(true); f:EnableMouse(true)
f:RegisterForDrag("LeftButton")
f:SetScript("OnDragStart", function() (this or f):StartMoving() end)
f:SetScript("OnDragStop", function() (this or f):StopMovingOrSizing() end)
f:SetBackdrop({ bgFile = "Interface\\DialogFrame\\UI-DialogBox-Background",
                edgeFile = "Interface\\DialogFrame\\UI-DialogBox-Border",
                tile = true, tileSize = 32, edgeSize = 32,
                insets = { left = 11, right = 12, top = 12, bottom = 11 } })
f:Hide()

local title = f:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
title:SetPoint("TOP", f, "TOP", 0, -18)
title:SetText("Herald")

local close = CreateFrame("Button", nil, f, "UIPanelCloseButton")
close:SetPoint("TOPRIGHT", f, "TOPRIGHT", -6, -6)

local status = f:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
status:SetPoint("TOP", title, "BOTTOM", 0, -6)

local big = CreateFrame("Button", "HeraldPlayButton", f, "UIPanelButtonTemplate")
big:SetWidth(200); big:SetHeight(28)
big:SetPoint("TOP", status, "BOTTOM", 0, -10)

local goalLabel = f:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
goalLabel:SetPoint("TOPLEFT", f, "TOPLEFT", 22, -100)
goalLabel:SetText("WHAT HERALD DOES")

local goalButtons = {}
local function makeGoal(i, g)
  local b = CreateFrame("Button", "HeraldGoal" .. i, f, "UIPanelButtonTemplate")
  b:SetWidth(100); b:SetHeight(22)
  local col = mod(i - 1, 2)
  local row = math.floor((i - 1) / 2)
  b:SetPoint("TOPLEFT", f, "TOPLEFT", 22 + col * 106, -116 - row * 26)
  b:SetText(g.label)
  b.goal = g.id
  b:SetScript("OnClick", function() Herald_SetGoal(g.id) end)
  b:SetScript("OnEnter", function()
    GameTooltip:SetOwner(b, "ANCHOR_RIGHT")
    GameTooltip:SetText(g.label)
    GameTooltip:AddLine(g.tip, 1, 1, 1, 1)
    GameTooltip:Show()
  end)
  b:SetScript("OnLeave", function() GameTooltip:Hide() end)
  goalButtons[i] = b
end
do
  local i
  for i = 1, table.getn(GOALS) do makeGoal(i, GOALS[i]) end
end

local stats = f:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
stats:SetPoint("TOPLEFT", f, "TOPLEFT", 22, -176)
stats:SetJustifyH("LEFT")
stats:SetWidth(210)

-- His last two choices, as the world server explains them ("Skipping Defias Thug: a pack of 3").
local choices = f:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
choices:SetPoint("TOPLEFT", f, "TOPLEFT", 22, -226)
choices:SetJustifyH("LEFT")
choices:SetWidth(210)

local hint = f:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
hint:SetPoint("BOTTOM", f, "BOTTOM", 0, 18)
hint:SetWidth(210)
hint:SetText("Hands off the keys while he plays: your input still moves the character.")

-- ------------------------------------------------------------------------------------------ minimap button
local mm = CreateFrame("Button", "HeraldMinimapButton", Minimap)
mm:SetWidth(31); mm:SetHeight(31)
mm:SetFrameStrata("MEDIUM")
mm:SetPoint("TOPLEFT", Minimap, "TOPLEFT", -6, -46)
local icon = mm:CreateTexture(nil, "BACKGROUND")
icon:SetTexture("Interface\\Icons\\Ability_Hunter_EagleEye")
icon:SetWidth(20); icon:SetHeight(20)
icon:SetPoint("CENTER", mm, "CENTER", 0, 1)
local ring = mm:CreateTexture(nil, "OVERLAY")
ring:SetTexture("Interface\\Minimap\\MiniMap-TrackingBorder")
ring:SetWidth(53); ring:SetHeight(53)
ring:SetPoint("TOPLEFT", mm, "TOPLEFT", 0, 0)
mm:SetHighlightTexture("Interface\\Minimap\\UI-Minimap-ZoomButton-Highlight")
mm:SetScript("OnClick", function() if f:IsShown() then f:Hide() else f:Show() end end)
mm:SetScript("OnEnter", function()
  GameTooltip:SetOwner(mm, "ANCHOR_LEFT")
  GameTooltip:SetText("Herald")
  GameTooltip:AddLine(H.active and "Playing this character. Click to open." or "Let Herald play this character.", 1, 1, 1, 1)
  GameTooltip:Show()
end)
mm:SetScript("OnLeave", function() GameTooltip:Hide() end)

-- ------------------------------------------------------------------------------------------ logic
-- What Herald is doing right now, for the panel: fighting, resting (and why), dead, or playing.
-- Resting matches classicplus_herald_ai.sql: below 70% health or 40% mana he eats, drinks or sits.
function Herald_Doing()
  if UnitIsDeadOrGhost("player") then return "on his way back (died)" end
  if UnitAffectingCombat("player") then return "fighting" end
  local hp = math.floor(100 * UnitHealth("player") / math.max(1, UnitHealthMax("player")))
  if hp < 70 then return "resting (health " .. hp .. "%)" end
  if UnitPowerType("player") == 0 and UnitManaMax("player") > 0 then
    local mp = math.floor(100 * UnitMana("player") / UnitManaMax("player"))
    if mp < 40 then return "resting (mana " .. mp .. "%)" end
  end
  return "playing"
end

local function refresh()
  if H.active then
    status:SetText("|cff5fd77aHerald is " .. Herald_Doing() .. "|r")
    big:SetText("Take back control")
  elseif H.available == false then
    status:SetText("|cffee6a5aSelf-bot is off on this realm|r")
    big:SetText("Let Herald play")
  else
    status:SetText("|cffb8995aYou are playing|r")
    big:SetText("Let Herald play")
  end
  local i
  for i = 1, table.getn(goalButtons) do
    if goalButtons[i].goal == (HeraldDB.goal or "level") then goalButtons[i]:LockHighlight() else goalButtons[i]:UnlockHighlight() end
  end
  local lines = "Goal: " .. goalById(HeraldDB.goal).label
  if H.started then
    lines = lines .. "\nTime: " .. clock(GetTime() - H.started)
      .. "    Kills: " .. H.kills .. "    Deaths: " .. H.deaths
      .. "\nXP: +" .. H.xp .. "    Money: +" .. money(H.money)
  end
  stats:SetText(lines)
  local n = table.getn(H.notes)
  if n > 0 then
    local t = H.notes[n]
    if n > 1 then t = H.notes[n - 1] .. "\n" .. t end
    choices:SetText(t)
  else
    choices:SetText("")
  end
end

-- A line from the world server about one of his choices (HeraldBrain.cpp: a whisper from his own
-- character that starts with "OVH:"; the chat filter above keeps it out of the chat window).
function Herald_Note(text)
  table.insert(H.notes, text)
  while table.getn(H.notes) > 2 do table.remove(H.notes, 1) end
  refresh()
end

-- Grouping: Herald groups with other Heralds on his own (the world server does that). An invite from a
-- friend or a guildmate while he plays is accepted; anyone else's waits for you.
local function knows(name)
  local i
  if GetNumFriends and GetFriendInfo then
    for i = 1, GetNumFriends() do
      if GetFriendInfo(i) == name then return true end
    end
  end
  if IsInGuild and IsInGuild() and GetNumGuildMembers and GetGuildRosterInfo then
    for i = 1, GetNumGuildMembers() do
      if GetGuildRosterInfo(i) == name then return true end
    end
  end
  return false
end

function Herald_SetGoal(id)
  HeraldDB.goal = id
  if H.active then
    orders(id)
  end
  refresh()
end

function Herald_Play()
  if H.active then return end
  H.asked = "on"
  send(".bot self")
end

function Herald_Stop()
  if not H.active then return end
  H.asked = "off"
  send(".bot self")
end

big:SetScript("OnClick", function() H.paused = nil; if H.active then Herald_Stop() else Herald_Play() end end)

-- One looter at a time. Every loot window the bot AI opens on the server comes to this client
-- too, and with auto loot on (Open Vanilla's default) the client swept it and let it go at the same
-- moment the bot AI was taking it: he stood at corpses and chests not knowing how to loot, and
-- your own looting failed while he played (players' reports, 2026-10-21). While he plays, auto
-- loot is off and the Loot addon shows no window (Herald_IsPlaying), so the bot AI loots alone;
-- your setting comes back when he stops, even after a disconnect (HeraldDB.autoLootWas).
local function cvar(name)
  if not GetCVar then return nil end
  local ok, v = pcall(GetCVar, name)
  if ok then return v end
end
local function setCvar(name, v)
  if SetCVar and v then pcall(SetCVar, name, v) end
end
local function autoLootOff()
  if HeraldDB.autoLootWas == nil then HeraldDB.autoLootWas = cvar("autoLootDefault") or false end
  setCvar("autoLootDefault", "0")
end
local function autoLootBack()
  if HeraldDB.autoLootWas == nil then return end
  if HeraldDB.autoLootWas then setCvar("autoLootDefault", HeraldDB.autoLootWas) end
  HeraldDB.autoLootWas = nil
end

function Herald_IsPlaying()
  return H.active and true or false
end

-- While he plays, the red error lines are his: the bot AI tries spells and targets and the realm
-- reports every refusal to this client ("Invalid target", "Out of range"...), which looked like
-- something you did wrong (a player's report, 2026-10-21). They stay off the screen while he plays.
local function quietErrors(e)
  return H.active and e == "UI_ERROR_MESSAGE"
end
if type(UIErrorsFrame_OnEvent) == "function" then
  local stockErrors = UIErrorsFrame_OnEvent
  UIErrorsFrame_OnEvent = function(e, msg, a2, a3, a4)
    if quietErrors(e or event) then return end
    return stockErrors(e, msg, a2, a3, a4)
  end
elseif UIErrorsFrame and UIErrorsFrame.GetScript then
  local stockScript = UIErrorsFrame:GetScript("OnEvent")
  if stockScript then
    UIErrorsFrame:SetScript("OnEvent", function()
      if quietErrors(event) then return end
      return stockScript()
    end)
  end
end

local function started(remote)
  autoLootOff()
  H.active = true
  H.available = true
  H.remote = remote
  H.started = GetTime()
  H.xp, H.kills, H.deaths, H.money = 0, 0, 0, 0
  H.lastMoney = GetMoney()
  H.lastXP, H.lastMax = UnitXP("player"), UnitXPMax("player")
  if remote then
    H.pendingGoal = HeraldDB.goal or "level"   -- Herald Autopilot sends its own plan; this sends only the fight orders
    H.wait = 2
    f:Show()
  else
    H.pendingGoal = HeraldDB.goal or "level"
    H.wait = 1.5      -- let the AI finish logging in before the first order
  end
end

local function stopped(text)
  H.active = false
  H.started = nil
  autoLootBack()
end

-- Shopping, the bank, the mailbox, a trainer, the auction house or a trade: Herald takes a break
-- while one of those is open, so he doesn't walk off and close it under you (a player's report,
-- 2026-10-21: the blacksmith's shop closed by itself). He plays on when it closes. The bot AI
-- never opens these itself (SAFE turns its vendor, bank and auction habits off), so an open one
-- is yours.
local BREAKS = {
  MERCHANT_SHOW = "MERCHANT_CLOSED", BANKFRAME_OPENED = "BANKFRAME_CLOSED", MAIL_SHOW = "MAIL_CLOSED",
  TRAINER_SHOW = "TRAINER_CLOSED", AUCTION_HOUSE_SHOW = "AUCTION_HOUSE_CLOSED", TRADE_SHOW = "TRADE_CLOSED",
}
local BREAK_ENDS = {}
for open, close in pairs(BREAKS) do BREAK_ENDS[close] = open end

local function takeBreak(e)
  if not H.active or H.paused or H.remote then return end
  H.paused = e
  Herald_Stop()
  msg("Taking a break while you're busy here. He plays on when you close it.")
end

local function endBreak(e)
  if not H.paused or BREAK_ENDS[e] ~= H.paused then return end
  H.paused = nil
  Herald_Play()
end

local ev = CreateFrame("Frame")
ev:RegisterEvent("VARIABLES_LOADED")
ev:RegisterEvent("PLAYER_ENTERING_WORLD")
ev:RegisterEvent("CHAT_MSG_SYSTEM")
ev:RegisterEvent("PLAYER_XP_UPDATE")
ev:RegisterEvent("PLAYER_MONEY")
ev:RegisterEvent("PLAYER_DEAD")
ev:RegisterEvent("CHAT_MSG_COMBAT_HOSTILE_DEATH")
ev:RegisterEvent("PLAYER_LEVEL_UP")
ev:RegisterEvent("CHAT_MSG_WHISPER")
ev:RegisterEvent("PARTY_INVITE_REQUEST")
ev:RegisterEvent("PARTY_MEMBERS_CHANGED")
for open, close in pairs(BREAKS) do ev:RegisterEvent(open); ev:RegisterEvent(close) end
ev:SetScript("OnEvent", function()
  local e, a1 = event, arg1
  if BREAKS[e] then takeBreak(e) return end
  if BREAK_ENDS[e] then endBreak(e) return end
  if e == "VARIABLES_LOADED" then
    HeraldDB.goal = HeraldDB.goal or "level"
    if not H.active then autoLootBack() end      -- he was playing when the game closed
    refresh()
  elseif e == "PLAYER_ENTERING_WORLD" then
    -- Also fires after every loading screen (a flight into another continent, a dungeon), where
    -- Herald keeps playing: give him his orders again once the new place has loaded.
    if H.active then H.pendingGoal = HeraldDB.goal or "level"; H.wait = 3 end
    refresh()
  elseif e == "CHAT_MSG_WHISPER" and a1 and arg2 == me() and string.find(a1, "^OVH:") then
    Herald_Note(string.sub(a1, 5))
  elseif e == "PARTY_INVITE_REQUEST" and H.active and a1 then
    if knows(a1) then
      AcceptGroup()
      if StaticPopup_Hide then StaticPopup_Hide("PARTY_INVITE") end
      Herald_Note("Joined " .. a1 .. "'s group")
    else
      Herald_Note("Invite from " .. a1 .. ": waiting for you to answer")
    end
  elseif e == "PARTY_MEMBERS_CHANGED" and H.active then
    -- joining a group can reset the bot AI's strategies, and the invite he already accepted may still be
    -- on screen: give the orders again and close it
    if GetNumPartyMembers and GetNumPartyMembers() > 0 and StaticPopup_Hide then StaticPopup_Hide("PARTY_INVITE") end
    H.pendingGoal = HeraldDB.goal or "level"; H.wait = 2
  elseif e == "PLAYER_LEVEL_UP" and H.active then
    H.pendingGoal = HeraldDB.goal or "level"; H.wait = 2
  elseif e == "CHAT_MSG_SYSTEM" and a1 then
    if string.find(a1, "Enable player ai", 1, true) then
      started(string.find(a1, "(Autopilot)", 1, true) and true or false)
    elseif string.find(a1, "Disable player ai", 1, true) then
      stopped()
    elseif string.find(a1, "Self-bot is disabled", 1, true) or string.find(a1, "permission to enable player ai", 1, true) then
      H.available = false
      msg("This realm hasn't turned self-bot on (AiPlayerbot.SelfBotLevel = 2), so Herald can't play here.")
    elseif H.asked and (string.find(a1, "no such command", 1, true) or string.find(a1, "Playerbot system is currently disabled", 1, true)) then
      H.available = false
      msg("This realm has no bot AI, so Herald can't play here.")
    end
    if H.asked and not string.find(a1, "player ai", 1, true) then H.asked = nil end
    refresh()
  elseif e == "PLAYER_XP_UPDATE" and H.active then
    local xp, max = UnitXP("player"), UnitXPMax("player")
    if H.lastXP then
      if max ~= H.lastMax then H.xp = H.xp + (H.lastMax - H.lastXP) + xp else H.xp = H.xp + (xp - H.lastXP) end
    end
    H.lastXP, H.lastMax = xp, max
  elseif e == "PLAYER_MONEY" and H.active then
    local m = GetMoney()
    if H.lastMoney and m > H.lastMoney then H.money = H.money + (m - H.lastMoney) end
    H.lastMoney = m
  elseif e == "PLAYER_DEAD" and H.active then
    H.deaths = H.deaths + 1
  elseif e == "CHAT_MSG_COMBAT_HOSTILE_DEATH" and H.active and a1 and string.find(a1, "^You have slain") then
    H.kills = H.kills + 1
  end
end)

-- Watchdog: if Herald stands in one spot for two minutes (not fighting, not dead), he is stuck on
-- terrain or a path: ask the bot AI to get unstuck and give it the goal again.
local WATCH_EVERY, STUCK_AFTER = 30, 120
local watchT, stillFor, lastX, lastY = 0, 0, nil, nil
local function watchdog(dt)
  if not H.active then watchT, stillFor, lastX = 0, 0, nil return end
  watchT = watchT + dt
  if watchT < WATCH_EVERY then return end
  watchT = 0
  local x, y = GetPlayerMapPosition("player")
  if not x or (x == 0 and y == 0) then return end
  -- resting (below 70% health or 40% mana: classicplus_herald_ai.sql sits him down) isn't stuck
  local hp = UnitHealth("player") / math.max(1, UnitHealthMax("player"))
  local mp = UnitManaMax("player") > 0 and UnitMana("player") / UnitManaMax("player") or 1
  local resting = (hp < 0.7 or (UnitPowerType("player") == 0 and mp < 0.4))
  local busy = UnitAffectingCombat("player") or UnitIsDeadOrGhost("player") or resting
  if lastX and not busy and math.abs(x - lastX) < 0.0005 and math.abs(y - lastY) < 0.0005 then
    stillFor = stillFor + WATCH_EVERY
  else
    stillFor = 0
  end
  lastX, lastY = x, y
  if stillFor >= STUCK_AFTER then
    stillFor = 0
    H.unstucks = (H.unstucks or 0) + 1
    send(".bot do " .. me() .. " unstuck")
    if not H.remote then H.pendingGoal = HeraldDB.goal or "level"; H.wait = 3 end
  end
end

local REORDER_EVERY = 300
local tick = 0
ev:SetScript("OnUpdate", function()
  local dt = arg1 or 0.1
  watchdog(dt)
  if H.pendingGoal then
    H.wait = H.wait - dt
    if H.wait <= 0 then
      orders(H.pendingGoal, H.remote)
      H.pendingGoal = nil
    end
  end
  if H.active and not H.pendingGoal then
    H.reorder = (H.reorder or 0) + dt
    if H.reorder >= REORDER_EVERY then H.reorder = 0; orders(HeraldDB.goal or "level", H.remote) end
  end
  tick = tick + dt
  if tick > 1 then
    tick = 0
    if f:IsShown() then refresh() end
  end
end)

SLASH_HERALD1 = "/herald"
SlashCmdList["HERALD"] = function(text)
  text = string.lower(text or "")
  if text == "play" or text == "start" then H.paused = nil; Herald_Play()
  elseif text == "stop" then H.paused = nil; Herald_Stop()
  elseif f:IsShown() then f:Hide()
  else f:Show() end
end

refresh()
