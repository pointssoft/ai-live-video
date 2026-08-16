# UI/UX Specification

## 1. উদ্দেশ্য

এই ডকুমেন্টে MimicMotion web application-এর information architecture, primary user flows, page/component behavior, camera recording UX, async generation status, error handling, accessibility, privacy এবং responsive/browser requirements নির্ধারণ করা হয়েছে।

Product real-time নয়। UI-এর মূল দায়িত্ব হলো user-কে একটি ভালো portrait এবং 5–15 সেকেন্ড motion clip তৈরি করতে সাহায্য করা, দীর্ঘ-running GPU process সম্পর্কে সৎ status দেওয়া এবং result/history নিরাপদে পরিচালনা করা।

## 2. UX principles

1. **Async expectation আগে থেকেই পরিষ্কার:** “Generate” চাপার পর কয়েক মিনিট অপেক্ষা হতে পারে; “live” বা “instant” শব্দ নয়।
2. **Capture quality guided:** Model failure কমাতে framing, lighting, single-person এবং motion নির্দেশনা recording-এর আগে।
3. **Progress honest, not fabricated:** Stage-based progress; exact শতাংশ নিশ্চিত না হলে false precision নয়।
4. **Recovery first:** Refresh, tab close, upload interruption বা network loss-এ job হারাবে না।
5. **Privacy visible:** Camera/portrait cloud processing এবং persistent storage consent-এর অংশ।
6. **Destructive action explicit:** Delete/cancel আলাদা; confirmation এবং consequence পরিষ্কার।
7. **Accessible by default:** Keyboard, screen reader, focus, contrast এবং reduced motion।
8. **Progressive disclosure:** Advanced model internals end user-কে দেখানো নয়; operational detail support section-এ।

## 3. Personas

### 3.1 Primary creator

- Dedicated GPU নেই বা যথেষ্ট VRAM নেই।
- Browser camera দিয়ে motion record করতে চায়।
- Portrait থেকে generated motion video পেতে চায়।
- ML parameter বোঝে না এবং বোঝার প্রয়োজন নেই।
- Result-এর জন্য অপেক্ষা করতে প্রস্তুত, যদি status এবং history reliable হয়।

### 3.2 Internal operator/support

MVP user UI-এর বাইরে হলেও requirements প্রভাবিত করে:

- Generation ID/job state দেখে issue diagnose করতে হবে।
- Raw secret/media access default নয়।
- User-friendly support reference ID দরকার।

## 4. Information architecture

```text
Public
├── Landing
├── Login
├── Register
├── Privacy
└── Terms

Authenticated
├── Dashboard
├── Create Generation
│   ├── Select Portrait
│   ├── Camera Setup
│   ├── Record Motion
│   ├── Review
│   ├── Upload
│   └── Submitted Status
├── Generations
│   └── Generation Details
├── Portraits
└── Settings
    ├── Account
    ├── Storage Usage
    └── Delete Account
```

## 5. Global navigation

Desktop authenticated shell:

```text
Logo | Dashboard | Create | History | Portraits     Storage | Account
```

Mobile:

- Compact header।
- Primary “Create” prominent।
- Drawer/bottom navigation implementation choice accessibility test অনুযায়ী।

Global elements:

- Connection/API error banner।
- Active generation indicator optional।
- User menu।
- Storage usage warning।
- Toast only transient confirmation-এর জন্য; important errors persistent inline/card হবে।

## 6. Authentication pages

### 6.1 Register

Fields:

- Email।
- Password।
- Confirm password।
- Terms/privacy acknowledgement।

Behavior:

- Client convenience validation + server authoritative errors।
- Password requirements input-এর কাছে।
- Duplicate email response account enumeration policy অনুযায়ী generic হতে পারে।
- Submit loading-এ duplicate click disabled, কিন্তু page frozen নয়।

### 6.2 Login

- Email/password।
- Password visibility toggle accessible label-সহ।
- Generic invalid credential message।
- Rate-limit message retry guidance-সহ।
- Successful login originally requested protected route বা Dashboard-এ।

### 6.3 Session expiry

- Unsaved local recording থাকলে immediate redirect-এর আগে warning/re-auth option বিবেচনা।
- Upload/generation already submitted হলে backend state safe; login-এর পর recover।

## 7. Dashboard

### Purpose

User দ্রুত নতুন generation শুরু, current jobs monitor এবং recent outputs দেখতে পারবে।

### Layout

1. Page title + `Create generation` primary CTA।
2. Active generations panel।
3. Recent completed generations grid/list।
4. Failed/action-needed items।
5. Storage usage summary।

### Empty state

```text
No generations yet
Upload a portrait and record a short motion clip to create your first video.
[Create generation]
```

Empty state-এ misleading sample output বা guaranteed quality statement নয়।

## 8. Create Generation wizard

Recommended single-route wizard with durable server IDs and local recording state। Stepper:

```text
1 Portrait -> 2 Camera -> 3 Record -> 4 Review -> 5 Generate
```

### 8.1 Step 1 — Select portrait

Options:

- Existing portrait select।
- New portrait upload।

Guidance card:

- One person।
- Clear face/body appearance।
- Good lighting।
- Avoid heavy obstruction।
- Sufficient resolution।
- Supported format/size।

Selected state:

- Large preview।
- Replace button।
- Validation status।
- Image crop হবে কিনা explanatory note।

Upload states:

```text
IDLE -> SELECTED -> UPLOADING -> VALIDATING -> READY
                         \-> FAILED
```

Next disabled until portrait `READY`।

### 8.2 Step 2 — Camera setup

Before permission:

```text
Camera access is needed only to record your motion clip.
The recording will be uploaded when you confirm Generate.
[Allow camera]
```

Permission request explicit user gesture-এর পর। Page load-এ surprise prompt নয়।

After permission:

- Camera preview।
- Camera selector (multiple devices হলে)।
- Mirror preview toggle; saved video orientation behavior স্পষ্ট।
- Framing overlay।
- Lighting/movement checklist।
- `Camera looks good` CTA।

Camera errors:

| Error | UI guidance |
|---|---|
| Permission denied | Browser site settings থেকে enable steps |
| No device | Camera connect/check, retry |
| Device busy | Other app/tab বন্ধ করতে বলবে |
| Insecure context | HTTPS/localhost requirement |
| Constraint failure | Lower supported constraints retry |
| Stream interrupted | Reconnect camera; no auto-submit |

### 8.3 Step 3 — Record motion

#### Pre-record checklist

- Only one person in frame।
- Stay within guide।
- Move at moderate speed।
- Avoid sudden camera movement।
- Clip must be 5–15 seconds।
- Output has no source audio।

#### Countdown

`3 → 2 → 1 → Recording`। Reduced motion preference-এ scale animation কমিয়ে text update। Countdown cancel করা যাবে।

#### Recording state

- Strong red/text indicator, color-only নয়।
- Elapsed `00:00 / 00:15`।
- Stop button।
- Stop disabled or warning before 5 sec; preferable: stop allowed, then too-short review error/retake।
- 15 sec-এ hard auto-stop।
- Route navigation/unload-এ recording in progress confirmation।

#### Recording compatibility

MIME selection priority capability-detected। UI implementation detail দেখাবে না; unsupported browser হলে:

```text
This browser cannot record a supported video format.
Try the latest Chrome, Edge, Firefox, or Safari.
```

### 8.4 Step 4 — Review

Side-by-side/wide layout:

- Selected portrait।
- Recorded motion video।

Metadata:

- Duration।
- Estimated upload size।
- Camera/source label optional।

Actions:

- `Retake` secondary।
- `Change portrait` link।
- `Generate video` primary।

Disclosure near CTA:

```text
Your portrait and recording will be uploaded for cloud GPU processing and saved to your private history until you delete them.
```

If clip <5 sec or >15 sec, Generate disabled এবং exact corrective message।

### 8.5 Step 5 — Upload/submission

Submission phases আলাদা দেখাতে হবে:

1. Preparing upload।
2. Uploading motion clip — determinate bytes percentage when available।
3. Verifying upload।
4. Submitting generation।
5. Waiting for GPU।

Upload progress এবং inference progress একই percentage bar-এ merge করা যাবে না; user 100% upload-কে completed generation ভাবতে পারে।

Upload cancel:

- Transfer abort and remain on Review।
- Runpod job submit হয়ে গেলে action becomes generation Cancel।

On successful submit:

- URL generation detail page-এ replace/navigate।
- Local camera Blob release when no longer needed।
- Refresh-safe durable state।

## 9. Generation status UX

### 9.1 User-facing status mapping

| Internal state/stage | Label | Description |
|---|---|---|
| `VALIDATING` | Checking your files | Format and duration verification |
| `SUBMITTING` | Starting generation | Securely creating GPU job |
| `QUEUED` | Waiting for GPU | Job is safely queued |
| `PREPARING_MEDIA` | Preparing motion | Video normalization |
| `EXTRACTING_POSE` | Reading movement | Pose processing |
| `GENERATING` | Generating video | MimicMotion GPU inference |
| `ENCODING` | Encoding result | Creating MP4 |
| `UPLOADING_OUTPUT` | Saving result | Persisting private output |
| `COMPLETED` | Ready | Playback/download available |
| `FAILED` | Generation failed | Actionable reason/retry if eligible |
| `TIMED_OUT` | Processing timed out | Retry/support guidance |
| `CANCELLED` | Cancelled | No output expected |

### 9.2 Progress presentation

- Stage timeline with completed/current/pending।
- Elapsed time।
- “You can leave this page; processing will continue.”
- Queue position না জানা থাকলে দেখানো যাবে না।
- Exact ETA benchmark-derived এবং wide range হলে “typically …” qualifier; otherwise omit।
- Diffusion percentage callback reliable হলে stage-local progress দেখানো যেতে পারে, total completion guarantee নয়।

### 9.3 Page refresh/network loss

- Status server থেকে rehydrate।
- Poll failure generation failure হিসেবে দেখানো যাবে না।
- Inline banner: “Connection lost. Your generation is still processing; retrying status…”
- Backoff এবং manual refresh button।
- Terminal state পেলে polling stop।

### 9.4 Background tab

- Document hidden হলে polling slow।
- Return করলে immediate refresh।
- Browser notification future opt-in; permission page load-এ চাওয়া নয়।

## 10. Generation detail page

### Header

- Generation date/time।
- Status badge।
- Short display ID/support reference।
- Contextual actions।

### Completed layout

- Generated output large player।
- Download MP4।
- Portrait and source motion expandable/reference cards।
- Generation metadata: duration, resolution, profile display name—not low-level secrets।
- Delete action danger zone।

### Processing layout

- Status timeline।
- Current stage।
- Elapsed time।
- Leave-page reassurance।
- Cancel action।

### Failed layout

- Human-readable summary।
- Recommended corrective action।
- Retry button only eligible হলে।
- “Record again” with portrait preserved।
- Support reference ID।
- Technical stack trace নয়।

## 11. Video playback

- HTML5 video controls।
- `playsInline`।
- Autoplay default off; surprising audio নেই, তবু browser rules সম্মান।
- Poster/thumbnail when available।
- Loading skeleton।
- Signed URL expired playback failure হলে transparent refresh and retry once।
- Range requests support; full file আগে download বাধ্যতামূলক নয়।
- Download button backend-authorized fresh signed URL নেবে।

If output lacks audio, UI silent/muted indicator optional; input audio preserve হবে এমন expectation তৈরি নয়।

## 12. Generation history

### List/card fields

- Output thumbnail বা processing placeholder।
- Created time।
- Status।
- Clip duration।
- Portrait thumbnail।
- Primary action: View।
- Overflow actions: cancel/retry/delete context অনুযায়ী।

### Filters

- All।
- Processing।
- Completed।
- Failed/cancelled।
- Date range optional after MVP baseline।

Use cursor pagination/infinite load; entire history এক request নয়। URL query-তে filters persist।

### Empty/filter states

- No history: create CTA।
- No match: clear filters।
- API error: retry, existing content preserve if cached।

## 13. Portrait library

- Upload new।
- Grid/list existing portraits।
- Ready/validating/invalid status।
- Select for generation।
- Delete।

Deletion dependency UX:

- Portrait linked generation থাকলে consequence স্পষ্ট।
- Preferred: portrait library থেকে hide/delete future use; historical generation references policy অনুযায়ী remain।
- Cascade media deletion হলে explicit list/count confirmation। Ambiguous single “Delete” নয়।

## 14. Settings and storage

### Account

- Email/profile basics।
- Logout sessions optional।
- Delete account danger zone।

### Storage usage

- Used / quota।
- Portrait, input clips, outputs breakdown where available।
- Near quota warning at configurable thresholds, e.g. 80%/95%।
- Link to history for deletion।

### Account deletion

Confirmation:

- Processing jobs cancelled।
- Portraits, inputs, outputs scheduled for deletion।
- Irreversible after grace period if applicable।
- Re-auth/password confirmation।

## 15. Cancellation UX

Cancel dialog:

```text
Cancel this generation?
If GPU processing has already started, used compute cannot be recovered. No generated output will be saved unless the job finishes before cancellation is confirmed.
[Keep processing] [Cancel generation]
```

Behavior:

- Confirm button pending state।
- UI stage `Cancelling…`।
- Final server response authoritative।
- Race-এ job completed হলে result দেখাবে এবং clear notice দিতে পারে: “The job completed before cancellation finished.”

## 16. Retry UX

Retry available হলে:

- Same portrait/motion reuse।
- New GPU attempt, extra processing time/cost implication।
- One click duplicate prevention।
- Previous failure history support metadata-তে থাকবে; user detail page latest attempt show, optional attempt history।

Input-invalid failure-এ Retry disabled; “Record again” বা “Choose another portrait” primary।

## 17. Delete UX

Generation deletion confirmation:

- Source motion এবং generated output private history থেকে delete হবে।
- Portrait separately retained কিনা স্পষ্ট।
- Processing job হলে প্রথমে cancel requirement।
- Async purge হলেও item immediately hidden/marked deleting।

Use typed confirmation only account-wide deletion-এর মতো high-impact case-এ; routine generation delete standard confirmation sufficient।

## 18. Error content guidelines

Error message structure:

1. কী হয়েছে।
2. User কী করতে পারে।
3. Retry button/action if safe।
4. Support reference if unresolved।

Examples:

### Pose not detected

```text
We couldn't read enough movement from this recording.
Record again with one person clearly visible, better lighting, and your body inside the guide.
[Record again]
```

### Upload interrupted

```text
The upload was interrupted. Your generation has not started.
Check your connection and try the upload again.
[Retry upload]
```

### GPU timeout

```text
The GPU job took longer than the allowed processing time.
You can retry this generation. If it happens again, use the support reference below.
[Retry generation]
Reference: ABC123
```

### Quota exceeded

```text
You have reached your storage or active generation limit.
Delete older media or wait for your current generation to finish.
[View history]
```

Avoid: “Unknown error”, raw HTTP status, Python/CUDA stack trace, Runpod secret IDs unless support-safe reference।

## 19. Camera and recording state model

```text
UNINITIALIZED
  -> PERMISSION_REQUIRED
  -> REQUESTING_PERMISSION
  -> READY
  -> COUNTDOWN
  -> RECORDING
  -> RECORDED
  -> REVIEWING
```

Error/recovery:

```text
PERMISSION_DENIED -> OPEN_SETTINGS_GUIDE -> RETRY
NO_DEVICE -> DEVICE_RETRY
DEVICE_BUSY -> RETRY
STREAM_INTERRUPTED -> RECONNECT
UNSUPPORTED -> BROWSER_GUIDANCE
```

State transitions component/hook tests-এ cover করতে হবে। Multiple `getUserMedia` streams leak করা যাবে না; camera switch-এ previous tracks stop।

## 20. Upload state model

```text
IDLE
 -> REQUESTING_URL
 -> UPLOADING
 -> VERIFYING
 -> READY
```

Failures:

- URL expired: replacement upload session/URL।
- Network abort: retry same valid URL where provider semantics safe, otherwise restart।
- Checksum mismatch: re-upload; inference নয়।
- Validation failure: corrective message।

Upload page close হলে browser upload বন্ধ হতে পারে; before-unload warning only active transfer-এ। Once generation submitted, leaving safe।

## 21. Responsive design

### Desktop

- Camera and instructions side-by-side।
- Review portrait/motion side-by-side।
- History grid।

### Tablet

- Two-column where width permits; controls touch-sized।

### Mobile browser

Web app target হলেও mobile camera behavior test করতে হবে:

- Portrait orientation default।
- Device camera selection may expose front/back labels only after permission।
- Full-screen camera preview not hide stop controls।
- Safe area insets।
- Large touch target minimum ~44 CSS px।
- Upload on unstable network recovery।

MVP officially supported device/browser matrix release-এর আগে প্রকাশ করতে হবে।

## 22. Accessibility requirements

- WCAG 2.1 AA target।
- Every input has visible label।
- Logical heading hierarchy।
- Keyboard reachable camera/upload/actions।
- Focus moves to step heading on wizard transition।
- Dialog focus trap এবং return focus।
- Status updates `aria-live="polite"`; rapid timer প্রতি second screen reader announce নয়।
- Recording start/stop accessible text এবং non-color indicator।
- Error summary + field association।
- Contrast-compliant badges/progress।
- Video controls keyboard usable।
- `prefers-reduced-motion` respected।
- Loading skeleton assistive tech-এ noise নয়।

Camera framing is visual; textual equivalent instructions দিতে হবে।

## 23. Privacy and consent UX

Camera permission-এর আগে:

- কেন camera প্রয়োজন।
- কখন recording শুরু হবে (explicit button-এর পর)।
- Preview automatically upload হবে না।
- Submit করলে cloud processing হবে।

Generate CTA-এর আগে:

- Portrait ও selected recording upload হবে।
- Private history-তে persistent থাকবে until user deletes।
- Third-party cloud GPU/object storage processing disclosure legal copy অনুযায়ী।
- Audio output-এ ব্যবহৃত/সংরক্ষিত হবে কি না নির্দিষ্টভাবে বলা; proposed normalization audio drops, browser capture ideally audio disabled।

Settings/history-তে deletion সহজে discoverable। Consent dark pattern নয়।

## 24. Performance UX

- Camera page initial bundle থেকে heavy dashboard/video libraries separate/lazy load।
- Portrait thumbnails optimized; private signed source cache policy carefully।
- History MP4 preload নয়; thumbnail only।
- Player `preload="metadata"` or controlled।
- Upload direct-to-storage।
- Poll request lightweight।
- Signed URL refresh silent once; repeated failure visible।
- Slow API-তে skeleton; submit actions immediate disabled state।

## 25. Browser compatibility plan

Minimum test matrix release-এর সময় current versions দিয়ে lock হবে:

- Chrome/Edge desktop।
- Firefox desktop।
- Safari macOS।
- Chrome Android।
- Safari iOS if declared supported।

Test features:

- `navigator.mediaDevices`।
- `getUserMedia`।
- `MediaRecorder.isTypeSupported`।
- Camera switch।
- Blob playback।
- Direct S3 CORS upload।
- Large upload progress/abort।
- Signed MP4 range playback।

Unsupported state proactive detect করতে হবে; recording শেষে surprise failure নয়।

## 26. Content and terminology

Use:

- “Portrait” বা localized equivalent।
- “Motion recording”।
- “Generation”।
- “Waiting for GPU”।
- “Processing may take several minutes।”

Avoid:

- “Live camera”।
- “Real-time output”।
- “Instant”।
- “Chunk” end-user terminology।
- “Latent”, “scheduler”, “DWPose” normal user flow-তে।

UI localization-ready string catalog ব্যবহার করবে; Bengali/English support product decision হলে layout longer text সহ test করতে হবে।

## 27. Analytics and telemetry boundaries

Allowed product events without media content:

```text
camera_permission_result
recording_started
recording_completed(duration_bucket)
upload_started/completed/failed
generation_submitted
status_terminal(success/failure_code)
cancel_requested
retry_requested
output_played/downloaded
generation_deleted
```

Do not collect:

- Portrait/video bytes or frames।
- Signed URLs।
- Raw filenames if avoidable।
- Camera labels containing sensitive device info beyond operational need।
- User email in third-party analytics events।

Consent/legal policy অনুযায়ী analytics।

## 28. Wireframe descriptions

### Create — Camera step

```text
┌──────────────────────────────────────────────────────────┐
│ Create video        1 Portrait  [2 Camera]  3 Record ... │
├────────────────────────────────┬─────────────────────────┤
│                                │ Camera setup            │
│      LIVE CAMERA PREVIEW       │ ✓ One person            │
│      + framing overlay         │ ✓ Good lighting         │
│                                │ ✓ Stay inside guide     │
│                                │ Camera: [select]        │
├────────────────────────────────┴─────────────────────────┤
│ [Back]                              [Camera looks good]   │
└──────────────────────────────────────────────────────────┘
```

### Create — Review step

```text
┌──────────────────────────────────────────────────────────┐
│ Review your inputs                                      │
├──────────────────────┬───────────────────────────────────┤
│ Portrait             │ Motion recording                  │
│ [image]              │ [video controls]                  │
│ [Change]             │ 00:12 · [Retake]                  │
├──────────────────────┴───────────────────────────────────┤
│ Cloud processing and persistent private storage notice  │
│ [Back]                                    [Generate]     │
└──────────────────────────────────────────────────────────┘
```

### Processing detail

```text
┌──────────────────────────────────────────────────────────┐
│ Generation ABC123                         Waiting for GPU │
│                                                          │
│ ✓ Upload complete                                        │
│ ✓ Files checked                                          │
│ ● Waiting for GPU                                        │
│ ○ Reading movement                                       │
│ ○ Generating video                                       │
│ ○ Saving result                                          │
│                                                          │
│ You can leave this page. Processing will continue.       │
│ [Cancel generation]                                      │
└──────────────────────────────────────────────────────────┘
```

## 29. UI acceptance criteria

### Camera

- Permission user gesture ছাড়া requested নয়।
- Denied/no device/busy/unsupported প্রত্যেকটির actionable state আছে।
- Track recording/page exit/camera switch-এ clean হয়।
- 15 sec hard stop এবং 5 sec minimum validation আছে।

### Upload

- Byte progress দেখায়।
- Upload failure inference start করে না।
- Duplicate Generate click duplicate generation তৈরি করে না।
- Active upload leave warning আছে।

### Async generation

- Refresh/relogin-এর পর current status ফিরে আসে।
- Network status error worker failure হিসেবে দেখায় না।
- User page ছাড়তে পারে।
- Terminal success-এ playable output এবং download।
- Cancel/retry eligibility backend truth অনুসরণ করে।

### History/privacy

- User শুধুমাত্র নিজের records দেখে।
- Persistent storage notice visible।
- Generation/media delete discoverable এবং confirm করা হয়।
- Storage quota usage visible before hard failure।

### Accessibility

- Full primary flow keyboard দিয়ে সম্ভব।
- Screen reader meaningful status পায়।
- Recording state color-only নয়।
- Dialog focus behavior correct।
- 200% zoom-এ content/action inaccessible হয় না।

## 30. UX QA checklist

- [ ] First-time user guidance ছাড়া flow বুঝতে পারে।
- [ ] Processing duration expectation submit-এর আগে পরিষ্কার।
- [ ] Permission denied recovery tested।
- [ ] 5, 15 এবং invalid durations tested।
- [ ] Camera switch and stream cleanup tested।
- [ ] WebM/MP4 browser variations tested।
- [ ] Upload interruption/URL expiry tested।
- [ ] Refresh at every generation stage tested।
- [ ] Webhook delay/missing state UI tested।
- [ ] Signed playback URL expiry recovery tested।
- [ ] Cancel-complete race tested।
- [ ] Retry/non-retryable errors tested।
- [ ] Empty, loading, error and quota states complete।
- [ ] Mobile touch and desktop keyboard tested।
- [ ] Privacy copy legal review complete।
- [ ] No UI claims live/real-time behavior।
