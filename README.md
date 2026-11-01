# JC2 no camera shake

Disables the camera shake in the Windows Steam build of Just Cause 2.

Running, reeling the grappling hook, gunfire, and explosions all add amplitude to one shake value on the camera manager. While that value is above zero, the game builds a random offset and mixes it into the view. This script makes that function return immediately. The run-camera and grapple-camera filters still frame the shot; they no longer shake it.

The change is three bytes in the executable you select. A copy is saved beside it as `JustCause2.exe.noshake-backup` the first time you patch.

## Run

Close the game, then from this folder:

```text
python jc2_no_camera_shake.py
```

A file dialog opens. Choose `JustCause2.exe` in the game folder (usually `steamapps\common\Just Cause 2`). If Steam's library list can be read, the dialog starts in that folder. Cancelling the dialog leaves the game unchanged.

You can also pass the executable directly:

```text
python jc2_no_camera_shake.py "D:\SteamLibrary\steamapps\common\Just Cause 2\JustCause2.exe"
```

Check without writing:

```text
python jc2_no_camera_shake.py --dry-run
```

Turn shake back on:

```text
python jc2_no_camera_shake.py --restore
```

Python 3.9 or newer is enough. Nothing else needs to be installed.

Verifying the game files in Steam replaces `JustCause2.exe` and brings the shake back. Run the script again after that.

If the script says the shake function was not found, the executable is not the build this was written against. It will not modify the file.
