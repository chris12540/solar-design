# Cached background integration

Decision: keep current manual editor/library unchanged while building a separate,
source-free input boundary. Do not enable real imagery loading yet.

1. Validate a versioned input manifest, original source dates/expiry, declared
   permissions, current/original hashes, pixel-center affine transforms, aligned
   raster grids, calibration points and any used elevation datum/offset.
2. Verify provided bytes without opening paths or fetching URLs. Exercise known
   synthetic grid coordinates, rotations, half-pixel offsets and expiry boundaries.
3. Establish native image registration from small pinned-artifact/API evidence.
   The existing host has `useMapView=false`, no imagery choices and no imagery
   provider. Leave these off. A synthetic-only underlay can be added after its
   native API is demonstrated, with no remote basemap fallback.
4. Before accepting external inputs, introduce separate expiry-aware source-case
   storage and an external-case format. Image bytes, source-derived native models,
   drafts, named checkpoints, imports and exports must all retain the earliest
   original expiry and refuse use after it. Existing v1 manual packages and
   permanent examples stay separate. Do not silently migrate them.
5. Only then adapt a permitted, unexpired local cache, verify decoded raster
   dimensions/values and independent coordinate/height controls, and expose a
   manual tracing workflow. Address acquisition, new paid calls, automatic roof
   generation and production evaluator changes remain outside this implementation.

Production inspection was source-only and read-only. Its scripts expect
`source_fetched_at`/`expires_at` in database cache rows and `aligned.transform` in
prepared rasters. No database query, pickle load, image read or cache acquisition
was performed. Existing cache availability, permissions and expiry were not
established. Never infer new retention time from a file's timestamp.

Manifest validation checks declarations and numerical consistency. It cannot
establish licensing permission, authenticate lineage, identify a CRS's true units,
or prove surveyed accuracy. Byte hashes identify supplied content, not ownership.
Decoding, reprojection and persistence enforcement remain separate required gates.

Implemented first boundary: `input-manifest.mjs` validates declarations, affine
calibration, original expiry, explicit operation permissions and byte identity.
`input-manifest-checks.mjs` passes 31 source-free checks and writes a known
16×12 m pixel-center grid under `runtime/input-contract/`. Original submillisecond
expiry strings are retained; effective JS expiry floors milliseconds rather than
extending retention. Async byte verification rechecks expiry after hashing.

This module is not connected to the editor. It does not decode images, resolve
CRS authority/units, authenticate rights or lineage, supply a trusted clock, or
enforce storage by itself. External non-expiring licenses are not yet supported.
External metadata used in tests is fictitious; only self-generated PNG bytes are
read/hashed. Real imagery remains unsupported.

Native API candidates observed without loading textures:

- `orthoImageResourceFromWorldfile(model, worldfile)` builds an ORTHO_IMAGE resource
  with URL, source, dimensions, metadata and the supplied world-file object.
- `createGroundTexture(model, resource)` creates a texture wrapper using native
  project origin and model active/disabled flags.
- `loadTexture(texture)` loads its URL and checks decoded dimensions against
  metadata before setting texture. Executed successfully with pinned generated PNG bytes.
- `setGroundTextures(textures)` installs the collection and signals rendering.

Synthetic registration is now proven by `synthetic-underlay-probe.cjs`, including
90° rotation, three pixel-center controls, outer origin, 16×12 m scale, center,
2D/3D render and removal. Native `custom` source takes a geographic affine
worldfile evaluated at pixel corners; the manifest takes editor-meter pixel
centers. The adapter derives degree-per-meter factors from the native default
worldfile helper, then converts center coordinates to corners explicitly. Native
worldfile/local parameters agree with the independently specified fixture.

Collection registration survives frames in the tested empty host without enabling
provider imagery or map view. This does not establish arbitrary provider refresh,
CRS reprojection, real-world registration, reflected/sheared rasters or persistence.
Probe pins generated PNG bytes, kind, dimensions and media type before validating
manifest and loading an immutable local Blob. Its pin prevents accidental real
cache use; it is not an authenticity system. No external URL is accepted.

Own server CSP now allows Blob fetches in `connect-src`, because the native loader
fetches bytes before creating its image-decoder Blob. External origins stay blocked.
Decoded dimensions are checked by the native loader. Prior blocked fetch was a CSP
failure, not proof that SVG decoding fails. Generated PNG replaces SVG for this
experiment; old artifacts remain preserved.

Next: opt-in built-in synthetic calibration background lifecycle, using own adapter
code and explicit transient status. Verify tracing coordinates, removal, fresh/New
and recovery behavior without serializing transient texture URLs into manual cases.
Do not expose real file/address input until all external lifetime gates below pass.
No remote URL or basemap fallback may be used to discover missing interfaces.

Real-source activation also needs immutable byte ownership after checksum, decode
validation, rechecks after async operations, earliest-expiry timers and all save,
clipboard/export/recovery paths. Removing a background must not silently remove
its source-derived design's expiry. Forking/renaming cannot renew retention.
Logs, previews and private test captures containing source data need the same
lifetime. Do not mix them with permanent synthetic fixtures.
