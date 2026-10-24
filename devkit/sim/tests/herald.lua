-- Herald/Herald.lua: the orders Herald gives the realm's bot AI when he plays your character.
local T, api = ...

local function said(env, from)
    local out = {}
    for i = (from or 0) + 1, table.getn(env.__chat_sent) do table.insert(out, env.__chat_sent[i].msg) end
    return out
end
local function find(lines, text)
    for _, l in ipairs(lines) do if string.find(l, text, 1, true) then return l end end
end

T.test("Herald: playing starts with the goal, the loot strategy and the fight orders (no flee)", function()
    local env = T.addon("Herald")
    local n = table.getn(env.__chat_sent)
    api.fire(env, "CHAT_MSG_SYSTEM", "Enable player ai")
    api.tick(env, 3)
    local lines = said(env, n)
    T.ok(find(lines, " nc +grind,"), "the Level up goal")
    T.ok(find(lines, "-maintenance"), "the safety list rides with the goal")
    T.ok(find(lines, " nc +custom::herald"), "loots every kill (classicplus_herald_ai.sql)")
    T.ok(find(lines, " co -flee,+potions"), "never runs from two mobs; drinks a potion instead")
    for _, l in ipairs(lines) do T.ok(string.len(l) <= 255, "every order fits the 1.12 chat limit: " .. l) end
end)

T.test("Herald: a level-up gives the orders again (the bot AI may have reset its strategies)", function()
    local env = T.addon("Herald")
    api.fire(env, "CHAT_MSG_SYSTEM", "Enable player ai")
    api.tick(env, 3)
    local n = table.getn(env.__chat_sent)
    api.fire(env, "PLAYER_LEVEL_UP", 12)
    api.tick(env, 3)
    T.ok(find(said(env, n), " co -flee,+potions"), "fight orders again after the level-up")
    T.ok(find(said(env, n), " nc +custom::herald"), "and the loot strategy")
end)

T.test("Herald: the orders go out again every five minutes while he plays", function()
    local env = T.addon("Herald")
    api.fire(env, "CHAT_MSG_SYSTEM", "Enable player ai")
    api.tick(env, 3)
    local n = table.getn(env.__chat_sent)
    api.tick(env, 310, 1)
    T.ok(find(said(env, n), " co -flee,+potions"), "re-sent on the timer")
    api.fire(env, "CHAT_MSG_SYSTEM", "Disable player ai")
    n = table.getn(env.__chat_sent)
    api.tick(env, 310, 1)
    T.no(find(said(env, n), ".bot cmd"), "nothing once you take back control")
end)

T.test("Herald: Herald Autopilot (the desktop app) keeps its own goal; Herald adds only the fight, loot and rest orders", function()
    local env = T.addon("Herald")
    local n = table.getn(env.__chat_sent)
    api.fire(env, "CHAT_MSG_SYSTEM", "Enable player ai (Autopilot)")
    api.tick(env, 3)
    local lines = said(env, n)
    T.ok(find(lines, " co -flee,+potions"), "fight orders")
    T.ok(find(lines, " nc +custom::herald"), "loot and rest added on top (a bot AI reset drops them)")
    for _, l in ipairs(lines) do
        T.no(string.find(l, " nc ", 1, true) and not string.find(l, " nc +custom::herald", 1, true), "no goal of his own over the app's plan (" .. l .. ")")
    end
end)

T.test("Herald: resting below 70% health isn't 'stuck'; standing still at full health is", function()
    local env = T.addon("Herald")
    local me = api.unit(env, "player")
    env.__map.x, env.__map.y = 0.42, 0.61
    api.fire(env, "CHAT_MSG_SYSTEM", "Enable player ai")
    api.tick(env, 3)
    me.health, me.healthMax = 40, 100                    -- sitting to heal (classicplus_herald_ai.sql)
    local n = table.getn(env.__chat_sent)
    api.tick(env, 200, 1)
    T.no(find(said(env, n), " unstuck"), "a resting Herald is left alone")
    me.health = 100
    n = table.getn(env.__chat_sent)
    api.tick(env, 200, 1)
    T.ok(find(said(env, n), " unstuck"), "still for two minutes at full health: unstuck")
end)

T.test("Herald: the panel says what he is doing: fighting, resting and why, or playing", function()
    local env = T.addon("Herald")
    local me = api.unit(env, "player")
    api.fire(env, "CHAT_MSG_SYSTEM", "Enable player ai")
    me.health, me.healthMax, me.mana, me.manaMax = 100, 100, 100, 100
    T.eq(env.Herald_Doing(), "playing")
    me.health = 54
    T.eq(env.Herald_Doing(), "resting (health 54%)")
    me.health, me.mana = 100, 30
    T.eq(env.Herald_Doing(), "resting (mana 30%)")
    me.combat = true
    T.eq(env.Herald_Doing(), "fighting")
end)

T.test("Herald: he doesn't talk; the bot AI's replies and self-whispers stay out of chat, other lines don't", function()
    local env = T.addon("Herald")
    local me = env.UnitName("player")
    local function line(ev, text, author)
        env.this, env.arg1, env.arg2 = env.ChatFrame1, text, author
        env.ChatFrame_OnEvent(ev)
        env.this, env.arg1, env.arg2 = nil, nil, nil
    end
    api.fire(env, "CHAT_MSG_SYSTEM", "Enable player ai")
    api.tick(env, 3)
    line("CHAT_MSG_SYSTEM", "Enable player ai")
    line("CHAT_MSG_SYSTEM", "Sending command nc +grind to player " .. me)
    line("CHAT_MSG_WHISPER", "Hello, I'm going to grind now", me)
    api.tick(env, 3)
    line("CHAT_MSG_SYSTEM", "Quest accepted: The Fargodeep Mine")
    line("CHAT_MSG_WHISPER", "lfg deadmines?", "Kyomai")
    local chat = api.chat_text(env)
    T.lacks(chat, "Enable player ai")
    T.lacks(chat, "Sending command")
    T.lacks(chat, "going to grind")
    T.lacks(chat, "Sit back and watch", "the addon itself says nothing while he plays")
    T.lacks(chat, ".bot cmd", "his orders never show as said lines")
    T.has(chat, "Quest accepted", "ordinary system lines still show")
    T.has(chat, "lfg deadmines?", "other players' whispers still show")
end)

T.test("Herald: the world server's notes on his choices show in the panel (last two), never in chat", function()
    local env = T.addon("Herald")
    local me = env.UnitName("player")
    api.fire(env, "CHAT_MSG_SYSTEM", "Enable player ai")
    api.tick(env, 3)
    local function whisper(text)
        env.this, env.arg1, env.arg2 = env.ChatFrame1, text, me
        env.ChatFrame_OnEvent("CHAT_MSG_WHISPER")
        env.this = nil
        api.fire(env, "CHAT_MSG_WHISPER", text, me)
    end
    whisper("OVH:Skipping Defias Thug: a pack of 3")
    whisper("OVH:Stuck for 25 s: picking another way")
    whisper("OVH:Grouped with Kyomai for The Fargodeep Mine")
    local panel = env.HeraldPanel
    local seen = {}
    for _, r in ipairs({ panel:GetRegions() }) do
        if r.GetText and r:GetText() then table.insert(seen, r:GetText()) end
    end
    local all = table.concat(seen, "\n")
    T.has(all, "Grouped with Kyomai", "the newest choice")
    T.has(all, "picking another way", "and the one before it")
    T.lacks(all, "Defias Thug", "only the last two")
    T.lacks(api.chat_text(env), "OVH:", "never in the chat window")
end)

T.test("Herald: while he plays, a friend's or guildmate's invite is accepted; a stranger's waits for you", function()
    local env = T.addon("Herald")
    local accepted = 0
    env.AcceptGroup = function() accepted = accepted + 1 end
    env.GetNumFriends = function() return 1 end
    env.GetFriendInfo = function(i) return "Kyomai" end
    api.fire(env, "CHAT_MSG_SYSTEM", "Enable player ai")
    api.tick(env, 3)
    api.fire(env, "PARTY_INVITE_REQUEST", "Stranger")
    T.eq(accepted, 0, "a stranger's invite isn't answered for you")
    api.fire(env, "PARTY_INVITE_REQUEST", "Kyomai")
    T.eq(accepted, 1, "a friend's invite is accepted")
    api.fire(env, "CHAT_MSG_SYSTEM", "Disable player ai")
    api.fire(env, "PARTY_INVITE_REQUEST", "Kyomai")
    T.eq(accepted, 1, "when you play, invites are yours")
end)

T.test("Herald: his combat orders carry his class rotation for his level band, the other bands off", function()
    local env = T.addon("Herald")
    local _, class = env.UnitClass("player")
    class = string.lower(class)
    local n = table.getn(env.__chat_sent)
    api.fire(env, "CHAT_MSG_SYSTEM", "Enable player ai")
    api.tick(env, 3)
    local co = find(said(env, n), " co -flee,+potions")
    T.ok(co, "the fight orders went out")
    local lv = env.UnitLevel("player")
    local band = lv >= 40 and 40 or (lv >= 20 and 20 or 1)
    T.has(co, "+custom::herald_" .. class .. "_" .. band, "his band's rotation on")
    for _, b in ipairs({ 1, 20, 40 }) do
        if b ~= band then T.has(co, "-custom::herald_" .. class .. "_" .. b, "band " .. b .. " off") end
    end
    T.ok(string.len(co) <= 255, "fits the chat limit")
end)

T.test("Herald: he takes a break while you shop (or bank, mail, train, trade) and plays on when you close it", function()
    local env = T.addon("Herald")
    api.fire(env, "CHAT_MSG_SYSTEM", "Enable player ai")
    api.tick(env, 3)
    local n = table.getn(env.__chat_sent)
    api.fire(env, "MERCHANT_SHOW")
    T.ok(find(said(env, n), ".bot self"), "hands control back, so he doesn't walk off and close the shop")
    T.has(api.chat_text(env), "Taking a break")
    api.fire(env, "CHAT_MSG_SYSTEM", "Disable player ai")
    n = table.getn(env.__chat_sent)
    api.fire(env, "BANKFRAME_CLOSED")
    T.no(find(said(env, n), ".bot self"), "another window closing doesn't end the break")
    api.fire(env, "MERCHANT_CLOSED")
    T.ok(find(said(env, n), ".bot self"), "the shop closes: he plays on")
    api.fire(env, "CHAT_MSG_SYSTEM", "Enable player ai")
    api.tick(env, 3)
    T.ok(find(said(env, n), " co -flee,+potions"), "with his orders again")
    -- shopping while you play yourself changes nothing
    api.fire(env, "CHAT_MSG_SYSTEM", "Disable player ai")
    n = table.getn(env.__chat_sent)
    api.fire(env, "MERCHANT_SHOW"); api.fire(env, "MERCHANT_CLOSED")
    T.no(find(said(env, n), ".bot self"), "no break when he isn't playing")
end)

T.test("Herald: taking back control during a break means he stays off when the shop closes", function()
    local env = T.addon("Herald")
    api.fire(env, "CHAT_MSG_SYSTEM", "Enable player ai")
    api.tick(env, 3)
    api.fire(env, "MAIL_SHOW")
    api.fire(env, "CHAT_MSG_SYSTEM", "Disable player ai")
    api.slash(env, "/herald stop")
    local n = table.getn(env.__chat_sent)
    api.fire(env, "MAIL_CLOSED")
    T.no(find(said(env, n), ".bot self"), "you said stop: he stays stopped")
end)

T.test("Herald: while he plays he is the only looter - auto loot off, ll trash - and your setting comes back", function()
    local env = T.addon("Herald")
    env.SetCVar("autoLootDefault", "1")
    local n = table.getn(env.__chat_sent)
    api.fire(env, "CHAT_MSG_SYSTEM", "Enable player ai")
    T.eq(env.GetCVar("autoLootDefault"), "0", "the client stops sweeping the bot AI's loot windows")
    T.ok(env.Herald_IsPlaying(), "the Loot addon can ask")
    api.tick(env, 3)
    T.ok(find(said(env, n), " ll trash"), "he picks up everything, greys included")
    api.fire(env, "CHAT_MSG_SYSTEM", "Disable player ai")
    T.eq(env.GetCVar("autoLootDefault"), "1", "your auto loot is back")
    T.ok(not env.Herald_IsPlaying())
    -- the game closed while he played: the next login puts it back
    api.fire(env, "CHAT_MSG_SYSTEM", "Enable player ai")
    T.eq(env.GetCVar("autoLootDefault"), "0")
    local env2 = api.relog(env)                      -- the client's settings carry over: still "0"
    T.eq(env2.GetCVar("autoLootDefault"), "1", "restored after a disconnect")
end)

T.test("Herald: while he plays, the realm's refusals of his tries stay off the screen", function()
    local env = T.client()
    local shown = {}
    env.UIErrorsFrame_OnEvent = function(e, msg) table.insert(shown, msg) end   -- the stock handler
    api.load_with_deps(env, "Herald")
    api.login(env)
    env.UIErrorsFrame_OnEvent("UI_ERROR_MESSAGE", "Invalid target")
    T.eq(table.getn(shown), 1, "yours show as always")
    api.fire(env, "CHAT_MSG_SYSTEM", "Enable player ai")
    env.UIErrorsFrame_OnEvent("UI_ERROR_MESSAGE", "Invalid target")
    T.eq(table.getn(shown), 1, "his don't (player report, 2026-10-21)")
    env.UIErrorsFrame_OnEvent("UI_INFO_MESSAGE", "Quest accepted")
    T.eq(table.getn(shown), 2, "info lines still show")
    api.fire(env, "CHAT_MSG_SYSTEM", "Disable player ai")
    env.UIErrorsFrame_OnEvent("UI_ERROR_MESSAGE", "Out of range")
    T.eq(table.getn(shown), 3, "back when you play")
end)

T.test("Herald: his orders keep the mount off for now (he travels on foot)", function()
    local env = T.addon("Herald")
    local n = table.getn(env.__chat_sent)
    api.fire(env, "CHAT_MSG_SYSTEM", "Enable player ai")
    api.tick(env, 3)
    T.ok(find(said(env, n), ",-mount"), "-mount rides with the goal")
    T.ok(not find(said(env, n), ",+mount"), "never +mount")
end)
