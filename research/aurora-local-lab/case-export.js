const SCHEMA = 'roof-lab-case/v1';
const VERSION = '1';

function normalizeCaseName(name) {
  if (name == null) return null; // Original v1 packages did not include names.
  if (typeof name !== 'string' || !name.trim() || name.length > 500 || /[\u0000-\u001f\u007f]/.test(name)) {
    throw new Error('Case name must contain 1–500 characters without control characters');
  }
  return name.trim();
}

async function sha256(text) {
  const bytes = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return [...new Uint8Array(bytes)].map(b => b.toString(16).padStart(2, '0')).join('');
}

export function geometryFromNative(native) {
  const buildings = native?.site_json?.buildings;
  if (!Array.isArray(buildings)) throw new Error('Native design has no building geometry');
  let holeTopologyComplete = true;
  const geometry = buildings.map((building, index) => {
    if (!Array.isArray(building.nodes) || !Array.isArray(building.faces)) throw new Error('Unsupported building geometry');
    const vertices = building.nodes.map(n => {
      if (![n.x, n.y, n.z].every(Number.isFinite)) throw new Error('Building contains nonfinite coordinates');
      return [n.x, n.y, n.z];
    });
    const ring = indices => {
      if (!Array.isArray(indices) || indices.length < 3 || !indices.every(i => Number.isInteger(i) && i >= 0 && i < vertices.length)) {
        throw new Error('Unsupported or invalid polygon vertex references');
      }
      return indices.map(i => [...vertices[i]]);
    };
    return {
      id: building.id ?? `building-${index}`, roofIds: building.roofs || [],
      faces: building.faces.map(face => {
        const known = Array.isArray(face.holes);
        if (face.holes != null && !known) throw new Error('Unsupported hole encoding; use native export');
        if (!known) holeTopologyComplete = false;
        return { id: face.id ?? null, sourceKey: face.source_key ?? null,
          vertices: ring(face.nodes), holes: known ? face.holes.map(ring) : null, holesKnown: known,
          nativePitchDegrees: Number.isFinite(face.pitch) ? face.pitch : null,
          nativeAzimuthDegrees: Number.isFinite(face.azimuth) ? face.azimuth : null };
      }),
      walls: (building.walls || []).map(wall => ({ id: wall.id ?? null, sourceKey: wall.source_key ?? null, vertices: ring(wall.nodes) })),
    };
  });
  if (!geometry.some(b => b.faces.length)) throw new Error('Draw a roof before exporting a test case');
  return { scope: 'native-computed-building-faces-and-walls', holeTopologyComplete,
    visibilityIndependentlyVerified: false, buildings: geometry };
}

export async function makeTestCase({ nativeDesignJson, caseId, engineArtifacts, importedFrom = null, name = null }) {
  if (typeof nativeDesignJson !== 'string' || typeof caseId !== 'string' || !caseId) throw new Error('Missing case identity or native design');
  if (!['cad-bundle.js', 'datamodel-api-js.wasm'].every(name => /^[a-f0-9]{64}$/i.test(engineArtifacts?.[name] || ''))) {
    throw new Error('Missing verified engine artifact identities');
  }
  const native = JSON.parse(nativeDesignJson);
  if (native?.format_version !== '3' || !native.system_json || typeof native.system_json !== 'object' || Array.isArray(native.system_json)) {
    throw new Error('Unsupported native model format');
  }
  const geometry = geometryFromNative(native);
  const algorithmFingerprint = await sha256(JSON.stringify({ schema: SCHEMA, version: VERSION,
    functions: [normalizeCaseName.toString(), sha256.toString(), geometryFromNative.toString(), makeTestCase.toString()] }));
  return {
    schema: SCHEMA, caseId, createdAt: new Date().toISOString(),
    ...(name == null ? {} : { name: normalizeCaseName(name) }),
    referenceStatus: 'unvalidated-manual-comparison', benchmarkCompatible: false,
    provenance: { kind: 'manual-local-unregistered', externalInputsRegistered: false,
      sourceLineageComplete: false, engineArtifacts,
      exporter: { version: VERSION, algorithmSha256: algorithmFingerprint,
        fingerprintKind: 'running-function-source-plus-schema-and-version' } },
    coordinates: { units: 'm', axes: ['editor-x', 'editor-y', 'up'], georeferenced: false,
      horizontalCRS: null, horizontalOrigin: null, verticalDatum: 'unverified-editor-relative-zero',
      orientationConvention: 'native-unregistered' },
    limitations: ['Not surveyed truth or independent roof accuracy evidence.',
      'Current DXF benchmark does not consume this package.',
      'Visibility and overlaps are native output, not independently verified.',
      'Trees, panels and obstructions remain in native design; they are not converted by the geometry view.'],
    nativeDesignJson, nativeDesignSha256: await sha256(nativeDesignJson), geometry, importedFrom,
  };
}

export async function validateTestCase(packet, engineArtifacts) {
  if (!packet || packet.schema !== SCHEMA || typeof packet.caseId !== 'string' || !packet.caseId ||
    !Number.isFinite(Date.parse(packet.createdAt))) throw new Error('Unsupported test case file');
  const name = normalizeCaseName(packet.name);
  const p = packet.provenance, c = packet.coordinates;
  if (p?.kind !== 'manual-local-unregistered' || p.externalInputsRegistered !== false || p.sourceLineageComplete !== false ||
    packet.referenceStatus !== 'unvalidated-manual-comparison' || packet.benchmarkCompatible !== false ||
    c?.units !== 'm' || c.georeferenced !== false || c.horizontalCRS !== null || c.horizontalOrigin !== null) {
    throw new Error('Only unregistered manual lab cases can be opened here');
  }
  if (p.exporter?.version !== VERSION || !/^[a-f0-9]{64}$/i.test(p.exporter.algorithmSha256 || '')) throw new Error('Unsupported exporter version');
  for (const name of ['cad-bundle.js', 'datamodel-api-js.wasm']) {
    if (!engineArtifacts?.[name] || p.engineArtifacts?.[name] !== engineArtifacts[name]) throw new Error('Test case uses a different editor version');
  }
  if (typeof packet.nativeDesignJson !== 'string' || packet.nativeDesignJson.length > 20 * 1024 * 1024 ||
    await sha256(packet.nativeDesignJson) !== packet.nativeDesignSha256) throw new Error('Test case checksum does not match');
  const native = JSON.parse(packet.nativeDesignJson);
  if (native?.format_version !== '3' || !native.system_json || typeof native.system_json !== 'object' || Array.isArray(native.system_json)) {
    throw new Error('Unsupported native model format');
  }
  const geometry = geometryFromNative(native);
  const canonical = value => {
    if (Array.isArray(value)) return value.map(canonical);
    if (value && typeof value === 'object') return Object.fromEntries(Object.keys(value).sort().map(k => [k, canonical(value[k])]));
    return value;
  };
  if (JSON.stringify(canonical(geometry)) !== JSON.stringify(canonical(packet.geometry))) throw new Error('Test case geometry does not match its model');
  return { name: name || 'Imported test case', nativeDesignJson: packet.nativeDesignJson, importedFrom: {
    caseId: packet.caseId, createdAt: packet.createdAt, nativeDesignSha256: packet.nativeDesignSha256,
    engineArtifacts: { 'cad-bundle.js': p.engineArtifacts['cad-bundle.js'], 'datamodel-api-js.wasm': p.engineArtifacts['datamodel-api-js.wasm'] },
    exporter: { version: p.exporter.version, algorithmSha256: p.exporter.algorithmSha256, fingerprintKind: p.exporter.fingerprintKind },
    referenceStatus: packet.referenceStatus, importedAt: new Date().toISOString(),
  } };
}
