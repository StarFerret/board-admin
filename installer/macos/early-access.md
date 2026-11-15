How to open StarFerret (early access build)
============================================

This copy of StarFerret is not signed by Apple yet, so your Mac asks you to
confirm it once. A signed version that opens with a double click is on the way.

Needs an Apple silicon Mac (M1 or newer), macOS 13 or newer, and an
administrator password for this one step.

1. Drag StarFerret into Applications.

2. Open StarFerret from Applications.
   macOS says it could not verify StarFerret. Click Done.
   (On macOS 13 or 14 you can instead right-click StarFerret, choose Open,
   then Open again, and skip to step 4.)

3. Open System Settings, then Privacy & Security. Scroll down to Security.
   Next to "StarFerret was blocked to protect your Mac", click Open Anyway
   and enter your Mac password. The button is there for about an hour after
   step 2.

4. Open StarFerret again and click Open. Click Install in the StarFerret window.

You only do this once. Afterwards StarFerret opens normally.

If there is no Open Anyway button, your company manages this Mac and does not
allow apps from outside the App Store or identified developers. Use the
one line Terminal install instead, or ask your IT team.

For IT people, the same thing in Terminal (removes the "downloaded from the
internet" mark from the app):

    xattr -dr com.apple.quarantine /Applications/StarFerret.app

Questions: hello@starferret.com
