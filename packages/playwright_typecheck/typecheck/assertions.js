// Fingerprints every `expect(...)` assertion in a Playwright spec, for
// `playwright_typecheck.assertion_changes` (self-healing's assertion guard:
// whatever a heal fixes, it may never change, add or remove an assertion).
//
// stdin:  {"old": "<spec source>", "new": "<spec source>"}
// stdout: {"old": ["<fingerprint>", ...], "new": [...]}  (source order)
//
// A fingerprint is the whole assertion — subject, `.not`/`.soft`/`.poll`/
// `.resolves`, matcher, expected arguments and options — as a canonical
// token stream (whitespace, comments, quote style and trailing commas don't
// count), prefixed with `await ` when it is awaited. When the subject starts
// from a variable (`expect(heading)`, `expect(row.first())`), the
// declarations it resolves to are appended, so an assertion's locator can't
// be changed indirectly through the variable either.

const ts = require('typescript')

function canonical(text) {
  const scanner = ts.createScanner(ts.ScriptTarget.Latest, /* skipTrivia */ true)
  scanner.setText(text)
  const tokens = []
  for (let kind = scanner.scan(); kind !== ts.SyntaxKind.EndOfFileToken; kind = scanner.scan()) {
    if (
      kind === ts.SyntaxKind.StringLiteral ||
      kind === ts.SyntaxKind.NoSubstitutionTemplateLiteral
    ) {
      tokens.push(JSON.stringify(scanner.getTokenValue()))
    } else {
      tokens.push(scanner.getTokenText())
    }
  }
  // A trailing comma is formatting, not meaning.
  return tokens
    .filter((tok, i) => !(tok === ',' && [')', ']', '}'].includes(tokens[i + 1])))
    .join(' ')
}

// True for `expect(...)`, `expect.soft(...)`, `expect.poll(...)` and any
// matcher chain hanging off one of them.
function rootsInExpect(call) {
  let cur = call.expression
  for (;;) {
    if (ts.isPropertyAccessExpression(cur) || ts.isCallExpression(cur)) cur = cur.expression
    else if (ts.isParenthesizedExpression(cur) || ts.isNonNullExpression(cur)) cur = cur.expression
    else return ts.isIdentifier(cur) && cur.text === 'expect'
  }
}

// The innermost `expect(...)` / `expect.soft(...)` call of a chain.
function expectCall(call) {
  let found = null
  let cur = call
  for (;;) {
    if (ts.isCallExpression(cur)) {
      const callee = cur.expression
      if (
        (ts.isIdentifier(callee) && callee.text === 'expect') ||
        (ts.isPropertyAccessExpression(callee) &&
          ts.isIdentifier(callee.expression) &&
          callee.expression.text === 'expect')
      ) {
        found = cur
      }
      cur = cur.expression
    } else if (ts.isPropertyAccessExpression(cur) || ts.isParenthesizedExpression(cur)) {
      cur = cur.expression
    } else {
      return found
    }
  }
}

function rootIdentifier(expr) {
  let cur = expr
  for (;;) {
    if (ts.isAwaitExpression(cur) || ts.isParenthesizedExpression(cur) || ts.isNonNullExpression(cur)) {
      cur = cur.expression
    } else if (
      ts.isPropertyAccessExpression(cur) ||
      ts.isElementAccessExpression(cur) ||
      ts.isCallExpression(cur)
    ) {
      cur = cur.expression
    } else {
      return ts.isIdentifier(cur) ? cur : null
    }
  }
}

// Lexical lookup: the nearest enclosing block/function/file that declares
// `name` with an initializer.
// ponytail: lexical only — a `let` reassigned after its declaration, a
// function parameter, or a locator built inside a helper function/page
// object isn't traced, so a heal could still change what such a subject
// points at. A fuller version would follow the subject's value with the
// TypeScript type checker (ts.createProgram + getSymbolAtLocation) or a
// small data-flow pass.
function findDeclaration(fromNode, name) {
  for (let scope = fromNode.parent; scope; scope = scope.parent) {
    let hit = null
    const visit = (node) => {
      if (hit) return
      if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name) && node.name.text === name) {
        if (node.initializer) hit = node.initializer
        return
      }
      // Don't descend into nested scopes — their declarations aren't visible here.
      if (node !== scope && (ts.isBlock(node) || ts.isFunctionLike(node))) return
      ts.forEachChild(node, visit)
    }
    if (ts.isBlock(scope) || ts.isSourceFile(scope) || ts.isFunctionLike(scope)) {
      ts.forEachChild(scope, visit)
      if (hit) return hit
    }
  }
  return null
}

function subjectDeclarations(call) {
  const expectNode = expectCall(call)
  if (!expectNode || expectNode.arguments.length === 0) return []
  const out = []
  const seen = new Set()
  let pending = [rootIdentifier(expectNode.arguments[0])]
  // Follow `const row = form.locator(...)` back through `form` too, a few hops deep.
  for (let depth = 0; depth < 5 && pending.length; depth++) {
    const next = []
    for (const ident of pending) {
      if (!ident || ident.text === 'page' || seen.has(ident.text)) continue
      seen.add(ident.text)
      const init = findDeclaration(call, ident.text)
      if (!init) continue
      out.push(`${ident.text} = ${canonical(init.getText())}`)
      next.push(rootIdentifier(init))
    }
    pending = next
  }
  return out
}

function isAwaited(node) {
  let parent = node.parent
  while (parent && ts.isParenthesizedExpression(parent)) parent = parent.parent
  return Boolean(parent && ts.isAwaitExpression(parent))
}

function fingerprints(source) {
  const sf = ts.createSourceFile('spec.ts', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS)
  const out = []
  const visit = (node) => {
    if (ts.isCallExpression(node) && rootsInExpect(node)) {
      // Only the outermost call of a chain: `expect(x)` inside
      // `expect(x).toBe(1)` is part of that one assertion.
      const continuesChain =
        ts.isPropertyAccessExpression(node.parent) && node.parent.expression === node
      if (!continuesChain) {
        const deps = subjectDeclarations(node)
        out.push(
          (isAwaited(node) ? 'await ' : '') +
            canonical(node.getText(sf)) +
            (deps.length ? `  [where ${deps.join('; ')}]` : ''),
        )
        return
      }
    }
    ts.forEachChild(node, visit)
  }
  visit(sf)
  return out
}

let input = ''
process.stdin.setEncoding('utf8')
process.stdin.on('data', (chunk) => (input += chunk))
process.stdin.on('end', () => {
  const { old: oldCode, new: newCode } = JSON.parse(input)
  process.stdout.write(JSON.stringify({ old: fingerprints(oldCode), new: fingerprints(newCode) }))
})
