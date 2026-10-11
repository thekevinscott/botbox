# node: raise minimum Node.js to 22

### Summary

The package now requires Node.js 22 or newer. Node 20 reached end-of-life on
2026-04-30, so the floor moves up to the lowest LTS still receiving updates.
(CI itself runs on Node 24.)

### Required changes

Upgrade to Node.js 22 or newer. Installing the CLI on Node < 22 now triggers
an `EBADENGINE` warning (and fails outright under
`npm install --engine-strict`).

### Deprecations removed

None.

### Behavior changes without code changes

None.

### Verification

```
node --version            # v22.x or newer
npx mynewproduct --version
```
