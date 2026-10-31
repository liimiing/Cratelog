-- Native mpv surface: a subdued played-area overlay and direct mouse seeking.
-- Runs on the same clock as the spectrum, including pause, seek and resize.
local mp = require 'mp'
local overlay = mp.create_osd_overlay('ass-events')
local active, dragging, preview = false, false, nil
local last_seek = nil
local last_visual = nil
local range_start, range_end = 0, -1
local function track_duration()
    local total = mp.get_property_number('duration', 0)
    return math.max(0, (range_end >= 0 and math.min(total, range_end) or total) - range_start)
end

local function draw()
    local w, h = mp.get_osd_size()
    local duration = track_duration()
    if not active or not w or w < 1 or h < 1 or duration <= 0 then
        if last_visual then overlay:remove(); last_visual = nil end
        return
    end
    local position = preview or (mp.get_property_number('time-pos', 0) - range_start)
    local x = math.floor(w * math.max(0, math.min(1, position / duration)))
    -- Do not invalidate the VO for subpixel motion or unchanged clock text.
    local visual = string.format('%d:%d:%d:%d:%d', w, h, x, math.floor(math.max(0,position)), math.floor(duration))
    if visual == last_visual then return end
    last_visual = visual
    overlay.res_x, overlay.res_y = w, h
    -- Alpha D2 keeps the fill dark and preserves the spectrum's readability.
    overlay.data = string.format(
        '{\\an7\\pos(0,0)\\bord0\\shad0\\1c&H9B9288&\\1a&HD2&\\p1}' ..
        'm 0 0 l %d 0 %d %d 0 %d{\\p0}', x, x, h, h)
    if x > 0 then
        overlay.data = overlay.data .. '\n' .. string.format(
            '{\\an7\\pos(0,0)\\bord0\\shad0\\1c&HAAA399&\\1a&H90&\\p1}' ..
            'm %d 0 l %d 0 %d %d %d %d{\\p0}', x-1, x, x, h, x-1, h)
    end
    local function clock(seconds)
        seconds = math.max(0, math.floor(seconds))
        return string.format('%02d:%02d', math.floor(seconds / 60), seconds % 60)
    end
    overlay.data = overlay.data .. '\n' .. string.format(
        '{\\an3\\pos(%d,%d)\\fs%d\\b1\\bord0\\shad0\\1c&HFFFFFF&\\1a&H60&}%s / %s',
        w-14, h-10, math.max(22, math.floor(h*.24)), clock(position), clock(duration))
    overlay:update()
end

local function target_at_mouse()
    local w = mp.get_osd_size()
    local x = mp.get_mouse_pos()
    local duration = track_duration()
    if not active or not w or w < 1 or duration <= 0 then return nil end
    return math.max(0, math.min(1, x / math.max(1, w-1))) * duration
end

local function seek(target)
    if target and target ~= last_seek then
        last_seek = target
        mp.commandv('seek', target + range_start, 'absolute+exact')
    end
end

mp.add_forced_key_binding('MBTN_LEFT', 'cratelog-spectrum-seek', function(event)
    if event.event == 'down' then
        dragging = true
        preview = target_at_mouse()
        last_seek = nil
        seek(preview)
    elseif event.event == 'up' then
        if dragging then seek(target_at_mouse()) end
        dragging, preview = false, nil
    end
    draw()
end, {complex = true})

mp.add_forced_key_binding('mouse_move', 'cratelog-spectrum-drag', function()
    if dragging then preview = target_at_mouse(); draw() end
end)
mp.add_forced_key_binding('mouse_leave', 'cratelog-spectrum-leave', function()
    if dragging then seek(preview) end
    dragging, preview = false, nil
    draw()
end)
-- The embedded video surface owns the pointer, so the player menu is opened from here.
mp.add_forced_key_binding('MBTN_RIGHT', 'cratelog-subtitle-menu', function()
    mp.commandv('script-message', 'cratelog-subtitle-menu')
end)

mp.register_event('file-loaded', function() active = true; draw() end)
mp.register_script_message('cratelog-range', function(first, last)
    range_start, range_end = tonumber(first) or 0, tonumber(last) or -1
    preview, last_seek = nil, nil
    draw()
end)
mp.register_event('end-file', function()
    active, dragging, preview, last_seek = false, false, nil, nil
    overlay:remove(); last_visual = nil
end)
for _, name in ipairs({'time-pos', 'duration', 'osd-dimensions'}) do
    mp.observe_property(name, 'native', draw)
end
