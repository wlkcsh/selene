on run argv
    if (count of argv) < 1 then
        return "error: missing action"
    end if
    set actionName to item 1 of argv

    tell application "Spotify"
        if not application "Spotify" is running then
            return "not_running"
        end if

        if actionName is "playpause" then
            playpause
            return (player state as string)
        else if actionName is "play" then
            play
            return "playing"
        else if actionName is "pause" then
            pause
            return "paused"
        else if actionName is "next" then
            next track
            return "ok"
        else if actionName is "previous" then
            previous track
            return "ok"
        else if actionName is "volume" then
            if (count of argv) >= 2 then
                set targetVol to (item 2 of argv as integer)
                if targetVol < 0 then set targetVol to 0
                if targetVol > 100 then set targetVol to 100
                set sound volume to targetVol
                return "ok"
            end if
            return "error: missing volume value"
        else if actionName is "status" then
            set pState to (player state as string)
            try
                set tName to (name of current track as string)
                set tArtist to (artist of current track as string)
                return pState & "|" & tName & "|" & tArtist
            on error
                return pState & "||"
            end try
        end if
    end tell
    return "unknown_action"
end run
