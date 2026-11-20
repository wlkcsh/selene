on run argv
    if (count of argv) < 1 then
        return "error: missing target URI"
    end if
    set targetURI to item 1 of argv
    set contextURI to ""
    if (count of argv) >= 2 then
        set contextURI to item 2 of argv
    end if

    tell application "Spotify"
        if not application "Spotify" is running then
            activate
            delay 1
        end if

        if targetURI starts with "spotify:track:" then
            try
                if contextURI is not "" and contextURI is not "none" then
                    play track targetURI in context contextURI
                else
                    play track targetURI
                end if
                delay 0.3
                if (player state as string) is "playing" then
                    return "playing"
                end if
            on error err
                return "error: " & err
            end try
            return "playing"
        else
            -- Search URI: navigate Spotify to search view; do NOT blindly unpause unrelated tracks
            open location targetURI
            return "opened_search"
        end if
    end tell
end run
