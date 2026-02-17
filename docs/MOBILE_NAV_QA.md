# Plan A — Mobile Bottom-Tab Navigation QA Checklist

## Route Mapping

| Tab Name  | Path        | Primary / Secondary | Bottom Tab | More Menu |
|-----------|-------------|---------------------|------------|-----------|
| Lobby     | `/lobby`    | Primary             | ✅ (🏠)    |           |
| Table     | `/table/:id`| Primary             | ✅ (🃏)    |           |
| Clubs     | `/clubs`    | Primary             | ✅ (🏆)    |           |
| Profile   | `/profile`  | Primary             | ✅ (👤)    |           |
| History   | `/history`  | Secondary           |            | ✅ (📜)   |
| Training  | `/training` | Secondary           |            | ✅ (🎯)   |
| Sign Out  | —           | Utility             |            | ✅ (🚪)   |

## Files Changed

| File | Reason |
|------|--------|
| `apps/web/index.html` | Added `viewport-fit=cover`, `maximum-scale=1`, `user-scalable=no` for iOS safe areas and zoom prevention |
| `apps/web/src/App.tsx` | Added `useIsMobile` + `showMoreMenu` state; desktop header gets `cp-desktop-only`; mobile renders `MobileTopBar` + `MobileBottomTabs` + `MobileMoreMenu`; content wrapper gets dynamic padding for fixed bars; toast position adjusted for mobile |
| `apps/web/src/design-tokens.css` | Added ~160 lines of mobile nav CSS: `.cp-mob-topbar`, `.cp-mob-bottomtabs`, `.cp-mob-tab`, `.cp-mob-more-*`, responsive visibility classes |

## New Files

| File | Purpose |
|------|---------|
| `apps/web/src/hooks/useIsMobile.ts` | `matchMedia`-based hook, breakpoint 768px, no JS resize measuring |
| `apps/web/src/components/mobile-nav/MobileTopBar.tsx` | Fixed top bar: hamburger menu, centered page title, connection dot + avatar |
| `apps/web/src/components/mobile-nav/MobileBottomTabs.tsx` | Fixed bottom tab bar: 5 tabs (Lobby, Table, Clubs, Profile, More) with active indicator |
| `apps/web/src/components/mobile-nav/MobileMoreMenu.tsx` | Bottom sheet: secondary routes (History, Training) + Sign Out; dismissible via backdrop/ESC |
| `apps/web/src/components/mobile-nav/index.ts` | Barrel export |

## Edge Cases Handled

- **Table view**: Bottom tabs hidden (table has its own `BottomActionBar`); top bar still shows for title context
- **Secondary route active**: "More" tab highlights when Clubs/History/Training is active
- **Sign out**: Accessible via More menu on mobile (desktop Sign Out button hidden on mobile)
- **Deep links**: If user navigates directly to `/clubs` on mobile, More tab highlights correctly
- **More menu dismiss**: Closes on ESC, backdrop tap, or route selection
- **Landscape**: Top bar shrinks; bottom tabs remain visible; content not overlapped

## QA Checklist

### Mobile Portrait (≤ 768px)
- [ ] Desktop top tab strip is hidden
- [ ] Mobile top bar visible with page title + hamburger + avatar
- [ ] Bottom tabs visible with 5 items: Lobby, Table, Clubs, Profile, More
- [ ] Tap each primary tab → navigates correctly, active state highlights
- [ ] Tap "More" → bottom sheet opens with History, Training, Sign Out
- [ ] Tap a secondary route → navigates, sheet closes, "More" tab highlights for secondary routes
- [ ] Tap backdrop → More sheet closes
- [ ] Press ESC → More sheet closes
- [ ] Content not hidden behind top bar (padding-top applied)
- [ ] Content not hidden behind bottom tabs (padding-bottom applied)
- [ ] AppLegalFooter visible above bottom tabs
- [ ] Navigate to Table → bottom tabs disappear, BottomActionBar works normally
- [ ] Navigate away from Table → bottom tabs reappear

### Mobile Landscape
- [ ] Same checks as portrait
- [ ] No horizontal scroll
- [ ] Bars don't overlap content

### iOS Safari
- [ ] Safe area insets respected (notch, home indicator)
- [ ] No input zoom (font-size >= 16px enforced)
- [ ] `viewport-fit=cover` working

### Android Chrome
- [ ] No horizontal scroll
- [ ] Bottom tabs above system nav bar
- [ ] Touch targets >= 44px

### Desktop (≥ 769px)
- [ ] Original top tab strip unchanged and visible
- [ ] Mobile top bar hidden
- [ ] Mobile bottom tabs hidden
- [ ] More menu hidden
- [ ] All 6 tabs in top strip work as before
- [ ] No visual regression
