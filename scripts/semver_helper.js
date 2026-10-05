#!/usr/bin/env node
// Batched semver helper. Reads a JSON array of tasks from stdin, writes a JSON
// array of results to stdout. Using Node's `semver` package (the same engine
// npm itself uses) so range satisfaction matches real npm behavior exactly,
// rather than approximating npm range syntax (^, ~, x-ranges, ||) in Python.
//
// Task shapes:
//   {"op":"satisfies","version":"1.2.3","range":"^1.0.0"}
//   {"op":"maxSatisfying","versions":["1.0.0","1.2.3"],"range":"^1.0.0"}
//   {"op":"validRange","range":"^1.0.0"}
//   {"op":"diff","a":"1.2.3","b":"1.9.0"}   // "major"|"minor"|"patch"|null-ish
//   {"op":"gt","a":"1.2.3","b":"1.0.0"}
//   {"op":"rsort","versions":["1.0.0","1.2.3"]}  // valid versions, descending
'use strict';
const semver = require('semver');

let input = '';
process.stdin.on('data', (d) => (input += d));
process.stdin.on('end', () => {
  let tasks;
  try {
    tasks = JSON.parse(input);
  } catch (e) {
    process.stdout.write(JSON.stringify({ error: 'bad_json_input: ' + e.message }));
    process.exit(1);
  }
  const out = tasks.map((t) => {
    try {
      switch (t.op) {
        case 'satisfies':
          return { ok: true, result: semver.satisfies(t.version, t.range, { includePrerelease: false }) };
        case 'maxSatisfying':
          return { ok: true, result: semver.maxSatisfying(t.versions, t.range, { includePrerelease: false }) };
        case 'validRange':
          return { ok: true, result: semver.validRange(t.range) !== null };
        case 'diff':
          return { ok: true, result: semver.diff(t.a, t.b) };
        case 'gt':
          return { ok: true, result: semver.gt(t.a, t.b) };
        case 'rsort':
          return { ok: true, result: semver.rsort(t.versions.filter((v) => semver.valid(v) !== null)) };
        case 'valid':
          return { ok: true, result: semver.valid(t.version) !== null };
        default:
          return { ok: false, error: 'unknown_op:' + t.op };
      }
    } catch (e) {
      return { ok: false, error: String(e.message || e) };
    }
  });
  process.stdout.write(JSON.stringify(out));
});
