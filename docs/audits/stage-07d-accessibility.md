# Stage 07D — Accessibility and Desktop Usability Audit

**Audit date:** 2026-07-27  
**Scope:** keyboard operation, focus, Qt accessibility metadata, status/error
communication, contrast, scaling, responsive layout, mouse/touchpad/drag-and-
drop, dialogs, tooltips, and localization readiness.  
**Method limitation:** static source audit. Screen-reader output, rendered
contrast, platform scaling, and assistive-technology behavior require the
runtime test plan below. No production code was changed.

## Executive assessment

Midgard uses mostly standard Qt/qfluentwidgets controls, which gives it a
better baseline than a fully custom canvas UI. Buttons, combos, switches,
sliders, tables, text edits, and file dialogs are generally keyboard-capable.
There are also useful shortcuts for video marking, frame stepping, deletion,
and retouch undo/redo.

However, accessibility is not designed as a system:

- no application code sets accessible names or descriptions;
- label/control buddy relationships are absent;
- icon-only zoom/tool controls rely on tooltips;
- custom upload and image/canvas interactions are mouse-first;
- progress/status changes are not deliberately announced;
- focus order and focus restoration are not managed;
- custom QSS does not define a consistent visible focus state;
- fixed pixel fonts, heights, rails, previews, and dialogs are vulnerable to
  150–200% text/display scaling;
- errors/status use color and log wording as part of their meaning;
- only English translation exists and many strings remain inline.

Accessibility remediation should start with semantic metadata and keyboard
paths, then responsive/scaling work, then verified screen-reader behavior.

## Findings by area

### Keyboard navigation

Positive evidence:

- standard buttons/combos/switches/sliders/tables accept keyboard focus by
  default;
- prompt uses Enter to generate and Shift+Enter for a newline;
- task tables support Delete and Backspace;
- video supports `[`, `]`, `\\`, Delete, arrows, Ctrl+arrows, and
  Shift+arrows;
- retouch canvas supports standard Undo/Redo;
- dialogs use standard accept/reject buttons.

Gaps:

- no documented global shortcuts for Open, Run, Cancel, Jobs, Settings, or
  Diagnostics;
- custom full-area upload panel is a `QWidget` with mouse handling and no
  explicit strong focus/key activation;
- clickable preview empty states may not be keyboard reachable;
- task context actions such as open location/reset/delete are optimized for
  right-click; no explicit keyboard menu/action surface is provided;
- canvas-based selection requires pointer coordinates; no alternative
  keyboard workflow is designed;
- punctuation video shortcuts are undiscoverable and keyboard-layout
  dependent;
- Ctrl+C is overridden at the main window to exit, conflicting with ordinary
  Copy expectations when focus propagation reaches the window;
- stop actions often require a confirmation dialog, but focus restoration to
  the originating control is not explicit.

### Tab order and focus

- There are no `setTabOrder()` calls or page-level tab-order maps.
- Dynamic visibility (Run ↔ Stop; hidden Save/Retouch/Compare; model install ↔
  uninstall) can move or destroy the focused widget without restoring focus.
- Page navigation does not explicitly set initial focus or preserve last focus.
- Model cards contain several trailing controls; visual and construction order
  may not match an intuitive card-by-card flow after controls hide/show.
- Settings is one long scroll; keyboard users must traverse many expert
  controls to reach output/update/About.
- Modal editors risk long tab cycles across toolbars, sliders, canvas, and
  footer without landmarks.
- Custom canvas has `StrongFocus`, but other custom preview/drop widgets do not.

### Focus visibility

The custom theme defines hover, pressed, checked, and disabled states, but no
shared `:focus`/`:focus-visible` treatment. qfluentwidgets may paint focus for
some controls, but custom button QSS with `!important`, custom cards, sliders,
tool buttons, table cells, and hyperlink-like labels must be verified.

Requirement: a 2 px minimum high-contrast focus indicator that is not clipped,
is distinct from selection/hover, and meets a 3:1 contrast ratio against
adjacent colors.

### Screen readers and semantic metadata

Static search found no calls to:

- `setAccessibleName`;
- `setAccessibleDescription`;
- `QAccessible` announcements/events;
- `QLabel.setBuddy`.

Consequences:

- icon-only zoom and editor tools may be announced only generically;
- model cards may expose disconnected labels, state, switches, and actions;
- tooltips are not a reliable accessible-name mechanism;
- “On” lacks model context when announced alone;
- progress bars may have a value but not task/phase context;
- custom painted upload/canvas/selection surfaces have no role/state/value;
- card group headings are visual labels, not navigable semantic landmarks;
- log color/HTML semantics are not represented as alert/status events.

### Status, progress, and errors

- progress bars include numeric percentages visually but phase context is in
  separate labels/logs;
- application status changes are not deliberately announced;
- timed InfoBars can disappear before a screen-reader user reaches them;
- cancellation can clear status without announcing “cancelled”;
- logs categorize entries by English substring and color;
- task status is also text, which is good, but state changes do not raise an
  accessibility notification;
- errors can appear in preview text, logs, dialogs, or InfoBars inconsistently.

The target Jobs/error framework should expose persistent text and emit one
polite status announcement for phase changes, assertive announcement for
blocking failure, and no announcement for high-frequency percentage updates.

### Color and contrast

Calculated token contrast (WCAG relative luminance):

| Foreground/background | Ratio | Finding |
|---|---:|---|
| `#898A8B` secondary / `#0F1113` page | 5.47:1 | Passes normal text AA |
| `#898A8B` secondary / `#16181B` card | 5.14:1 | Passes normal text AA |
| `#7C3AED` primary / `#0F1113` page | 3.32:1 | Fails 4.5:1 for normal text; only suitable for large text/non-text |
| `#7C3AED` primary / `#16181B` card | 3.12:1 | Same risk |
| white / `#7C3AED` primary button | 5.70:1 | Passes normal text AA |
| red `#EF4444` / card | 4.73:1 | Passes normal text AA, close enough to require rendered-state checks |
| amber/green/blue status / card | 8.28–8.64:1 | Strong text contrast |

Additional issues:

- `#2A2D31` borders against dark backgrounds are likely too subtle to identify
  component boundaries/focus alone;
- primary purple is used for links and selection; normal-size linked text may
  fail even though underlining helps identify it;
- risk/status colors require text labels, which exist for risk badges but not
  necessarily every icon/progress state;
- transparent-preview checkerboard must be tested with selection/mask overlays;
- error/success parsing changes log color based on English words, creating
  localization and semantics defects.

### Text scaling and typography

- many sizes are pixel values as low as 8–10 px for card details, risk badges,
  rail titles, and statuses;
- setting cards have fixed 72 px height and content is truncated to a one-line
  summary/tooltip;
- navigation items and buttons have fixed heights;
- the log pane has fixed 100 px height;
- prompt has fixed 90 px height;
- modal confirm content is wrapped by estimated character count and dialog
  widget gets a fixed size;
- detailed editor labels use 9 px;
- increasing the system font can clip rather than reflow.

Text must remain complete and operable at 200% text scaling. Tooltips are not an
acceptable substitute for clipped descriptions.

### High-DPI and platform scaling

Positive:

- QApplication sets `HighDpiScaleFactorRoundingPolicy.PassThrough`;
- Qt 6 generally handles device-independent pixels and icon pixmaps.

Risks:

- UI tokens and window/dialog dimensions are hardcoded pixels;
- primary screen is used to center the window, not necessarily the screen where
  launch occurred;
- fixed 960/640 preview widths and 16:9 fixed heights can exceed small/scaled
  displays;
- the 300 px right rail does not collapse/reflow;
- 200 px Home side padding plus three 220 px combos is unsuitable for narrow
  windows;
- retouch dialogs request 1200×800 and only some presentation logic adapts;
- custom painted borders/handles may become visually thin or mis-sized at
  fractional scale;
- multi-monitor moves with different scale factors need pixmap/cache refresh
  testing;
- icon resources must be inspected for device-pixel-ratio sharpness.

### Minimum window size and responsive layout

The default 1280×750 is clamped to the screen, but no useful minimum layout
contract is established. Workspaces keep a fixed right rail and fixed log
height. At small sizes or high scaling, preview, task list, and actions compete
without a responsive breakpoint.

Target breakpoints:

```text
wide: preview + right rail
medium: narrower/collapsible rail, settings above tasks
narrow/high-scale: single-column scroll, preview -> settings -> tasks -> actions
```

Never make Run/Cancel or current status inaccessible below the fold without a
stable action footer.

### Reduced motion

Midgard already disables page-switch and combo popup animation, partly for
Linux flicker. It does not query an OS reduced-motion preference or centralize
animation duration. Remaining qfluentwidgets InfoBar, navigation, progress, and
dialog animations should respect:

```text
System preference -> application reduced-motion override -> component policy
```

Reduced motion should replace spatial movement with immediate state changes,
not remove progress feedback.

### Mouse, touchpad, and drag-and-drop

- drag-and-drop accepts files across preview panels and gives hover feedback;
- zoom uses wheel and tool buttons;
- selection handles and brush tools are pointer-oriented;
- no touch-specific gestures or target-size policy is defined;
- medium buttons are 32 px and small buttons 24 px, below a comfortable 44×44
  touch target;
- tooltips are mouse-hover dependent;
- horizontal/trackpad scroll and pinch zoom behavior are not specified;
- dropping unsupported files writes errors to logs rather than a strong inline
  summary;
- drag operations need a non-drag keyboard/file-dialog equivalent everywhere.

### File dialogs

Native Qt file dialogs provide a baseline, but:

- initial directories are inconsistent;
- image Save dialogs can start with bare filenames;
- output destination and overwrite policy are not previewed before processing;
- filters and validation vary by tool;
- there is no recent-output picker;
- errors after dialog acceptance may be log-only.

Retain native dialogs unless platform testing finds a blocker. Always provide a
normal button with an accessible name; drag-and-drop remains optional.

### Tooltip usability

Many descriptions live only in tooltips:

- Settings group descriptions;
- truncated detailed card content;
- zoom/editor icon controls;
- full task paths;
- risk explanations.

Tooltips are transient, difficult for touch users, and inconsistently exposed
to assistive technology. Essential content must be inline or available through
a keyboard-operable Help/Details control. Tooltip delays and wrapping need
platform tests.

### Localization readiness

Positive:

- a large share of copy uses `backend/interface/en.ini`;
- ConfigParser interpolation is disabled for percent signs.

Gaps:

- only English is loaded and the file path is fixed;
- multiple fallback/diagnostic/error strings are inline English;
- On/Off strings are hardcoded in shared cards;
- log classification searches English words;
- layouts assume English widths and truncate descriptions;
- sentence fragments are concatenated with model names/statuses;
- file filters and technical messages are not consistently translated;
- no pluralization, locale number formatting, RTL layout, or translator
  context;
- punctuation shortcuts and text wrapping assumptions are locale-sensitive.

## Required keyboard workflows

Target application map:

| Goal | Required path |
|---|---|
| Navigate pages | Tab/Shift+Tab within navigation, arrows among routes, Enter/Space activate; optional Ctrl+1… routes |
| Select input | `Ctrl+O` opens context-appropriate file dialog; focused drop zone activates with Enter/Space |
| Choose model | Tab to labeled combo, arrows/type-ahead, selection announced with compatibility |
| Change preset | Labeled segmented/radio control; arrows and Space |
| Run | `Ctrl+Enter` or explicit Run button; disabled reason announced |
| Cancel | `Esc` requests cancel only when job/editor context is active; confirmation focus safe |
| Settings | `Ctrl+,` |
| Jobs | documented shortcut such as `Ctrl+J` |
| Diagnostics | Help menu/route and documented shortcut |
| Close dialog | Esc returns focus to opener |
| Error details | Focus moves to persistent error card; Details and Copy Diagnostics reachable |

Do not bind plain Ctrl+C to exit. Preserve platform-standard Copy; use the
normal close shortcut/menu.

## Screen-reader improvements and Qt properties

### Required properties

| Control | `accessibleName` | `accessibleDescription` / behavior |
|---|---|---|
| Nav route | Visible route label | Current page state |
| Model combo | “Model for Remove Background” | Current install/compatibility requirements |
| Preset control | “Processing preset” | Effect of selected preset |
| Icon-only button | Localized action, e.g. “Zoom in” | Shortcut and effect |
| Model switch | “Enable BiRefNet General” | Installed/selected/loaded distinction |
| Install/uninstall | Include model name | Size, destructive effect |
| Progress bar | “Overall progress for <job>” | Phase, value; rate-limited changes |
| Task table | Meaningful table name | Row state and available actions |
| Drop zone | “Select or drop input files” | Accepted formats; Enter/Space opens dialog |
| Canvas | Tool, image, selection summary | Alternative list/numeric controls where feasible |
| Error card | Error title | Recommended action; focusable Details |

Use `QLabel.setBuddy(control)` for visible form labels. Set explicit
`accessibleDescription` for disabled reasons because ordinary tooltips may not
be read. Dynamic state changes should update both name/description and emit an
appropriate Qt accessibility event after confirming PySide6 support on each
platform.

### Announcements

- polite: queued, phase changed, model ready, save complete;
- assertive: blocking error or job failed;
- no announcement for each 1% increment;
- announce cancellation requested and cancellation complete separately;
- when a button becomes disabled, do not move focus unexpectedly; announce the
  reason in a status region.

## Focus-order issues and target order

Per tool:

```text
page heading
-> input/select-files
-> preset
-> essential settings
-> task list
-> Run
-> active progress/Cancel
-> result actions
-> optional log/details
```

Current visual layout places preview left and settings/tasks/actions right;
automatic construction order may not match this conceptual path. Define it
explicitly at each responsive breakpoint.

For dialogs:

```text
dialog title -> tool choice -> tool options -> canvas -> history/actions
-> primary Save/Done -> Cancel
```

On opening, focus the first meaningful control. On closing, restore focus to
the exact button/canvas action that opened it.

## High-DPI and responsive requirements

- use font-relative metrics or Qt layout size hints, not fixed text/card
  heights;
- cards grow vertically and show full descriptions;
- buttons meet at least 32×32 desktop pointer target and 44×44 where touch mode
  is supported;
- cap content widths but allow controls to wrap/stack;
- add responsive workspace breakpoints;
- compute dialog size from target screen available geometry and size hints;
- handle `screenChanged`/DPI changes and refresh raster assets;
- test 100%, 125%, 150%, 175%, 200%, 250% on Windows;
- test Retina and non-Retina multi-monitor movement on macOS;
- test X11/Wayland scale 1, 1.25/1.5 where supported, and 2;
- ensure custom selection handles remain visible and hittable.

## Accessibility test plan

### Automated

- widget-tree lint: every enabled interactive widget has non-empty accessible
  name; icon-only controls cannot rely only on tooltip;
- label-buddy tests for every form field;
- tab traversal tests detect unreachable controls, cycles, and hidden-widget
  focus;
- shortcut conflict tests against standard Qt/platform bindings;
- token contrast tests at AA thresholds;
- screenshot/layout tests at multiple window sizes, translations, and scale
  factors;
- tests that status/error meaning remains in text with color removed;
- tests that disabled controls have a reason string;
- translation extraction test forbids new user-facing inline strings.

### Manual assistive technology

- Windows: Narrator and NVDA at 100/150/200%;
- macOS: VoiceOver with Retina and keyboard navigation;
- Linux: Orca on a supported desktop/Qt accessibility bridge;
- keyboard-only completion of onboarding, every tool, model install, errors,
  save/open, Jobs, Settings, and Diagnostics;
- high contrast themes and color-vision simulations;
- reduced-motion settings;
- mouse, touchpad, and optionally touch target/gesture checks.

### Scenario matrix

- empty, downloading, incompatible, offline, worker failed, model corrupt;
- active progress and cancellation;
- modal confirmation, editor, and error details;
- long filenames, very long translated strings, RTL smoke test;
- focus restoration after page switch, dialog close, job completion, and
  dynamic Run/Stop replacement.

## Incremental implementation backlog

### P0 — Semantics and blockers

- restore standard Ctrl+C behavior;
- give all icon-only/custom controls accessible names;
- make upload/drop panels focusable and keyboard activatable;
- add label buddies and disabled reasons;
- add persistent structured error/status regions;
- establish visible focus tokens.

### P1 — Complete keyboard paths

- define per-page tab order and focus restoration;
- add Open/Run/Cancel/Settings/Jobs/Diagnostics shortcuts;
- expose task context actions without right-click;
- add keyboard alternatives or explicit limitations for canvas selection;
- announce job phases and failures.

### P1 — Scaling/responsiveness

- remove fixed text/card/dialog heights;
- introduce workspace breakpoints and scroll-safe action placement;
- raise tiny fonts/targets;
- validate multi-monitor DPI and custom-painted controls.

### P2 — Visual and localization quality

- adjust primary link/focus colors to meet contrast;
- strengthen boundary/focus contrast;
- move essential tooltip content inline;
- centralize all strings, pluralization, locale formats, and RTL behavior;
- honor reduced-motion preference.

## Acceptance criteria

- Every interactive control has an accessible localized name; every icon-only
  control has explicit semantics.
- All required workflows complete keyboard-only without focus loss/trap.
- Focus is always visible and restored after dynamic changes/dialogs.
- Status, progress, and errors are understandable without color and announced
  at appropriate frequency.
- Normal text and UI indicators meet WCAG AA contrast targets.
- No essential information exists only in a tooltip.
- UI remains readable/operable at 200% text and display scaling.
- Workspaces adapt to small windows instead of clipping essential actions.
- Standard platform shortcuts retain their expected meaning.
- Screen-reader tests pass on Windows, macOS, and the supported Linux desktop.

