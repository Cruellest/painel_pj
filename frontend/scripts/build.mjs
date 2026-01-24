/**
 * Build Script - Portal PGE Frontend
 *
 * Transpila arquivos TypeScript para JavaScript usando esbuild.
 * Os arquivos JS resultantes são colocados nas pastas templates/ de cada sistema.
 */

import * as esbuild from 'esbuild';
import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const ROOT_DIR = path.resolve(__dirname, '..');
const SRC_DIR = path.join(ROOT_DIR, 'src');
const SISTEMAS_DIR = path.resolve(ROOT_DIR, '..', 'sistemas');

// Cores para output
const colors = {
  reset: '\x1b[0m',
  green: '\x1b[32m',
  yellow: '\x1b[33m',
  blue: '\x1b[34m',
  red: '\x1b[31m',
  cyan: '\x1b[36m',
};

function log(message, color = 'reset') {
  console.log(`${colors[color]}${message}${colors.reset}`);
}

/**
 * Encontra todos os arquivos TypeScript para compilar
 */
function findEntryPoints() {
  const entryPoints = [];

  // 1. Arquivos de sistemas (src/sistemas/*)
  const sistemasDir = path.join(SRC_DIR, 'sistemas');
  if (fs.existsSync(sistemasDir)) {
    const sistemas = fs.readdirSync(sistemasDir, { withFileTypes: true })
      .filter(d => d.isDirectory())
      .map(d => d.name);

    for (const sistema of sistemas) {
      const sistemaDir = path.join(sistemasDir, sistema);
      const tsFiles = fs.readdirSync(sistemaDir)
        .filter(f => f.endsWith('.ts') && !f.endsWith('.d.ts'));

      for (const tsFile of tsFiles) {
        entryPoints.push({
          input: path.join(sistemaDir, tsFile),
          output: path.join(SISTEMAS_DIR, sistema, 'templates', tsFile.replace('.ts', '.js')),
          sistema,
        });
      }
    }
  }

  // 2. Arquivos globais (src/shared/* -> frontend/static/js/)
  const sharedDir = path.join(SRC_DIR, 'shared');
  if (fs.existsSync(sharedDir)) {
    const tsFiles = fs.readdirSync(sharedDir)
      .filter(f => f.endsWith('.ts') && !f.endsWith('.d.ts'));

    for (const tsFile of tsFiles) {
      entryPoints.push({
        input: path.join(sharedDir, tsFile),
        output: path.join(ROOT_DIR, 'static', 'js', tsFile.replace('.ts', '.js')),
        sistema: 'shared',
      });
    }
  }

  return entryPoints;
}

/**
 * Build de um único arquivo
 */
async function buildFile(entry) {
  const outputDir = path.dirname(entry.output);

  // Garante que o diretório de output existe
  if (!fs.existsSync(outputDir)) {
    fs.mkdirSync(outputDir, { recursive: true });
  }

  try {
    await esbuild.build({
      entryPoints: [entry.input],
      outfile: entry.output,
      bundle: true,
      format: 'iife',
      target: ['es2020'],
      minify: process.env.NODE_ENV === 'production',
      sourcemap: process.env.NODE_ENV !== 'production',
      // Define variáveis globais do browser
      define: {
        'process.env.NODE_ENV': JSON.stringify(process.env.NODE_ENV || 'development'),
      },
      // Externaliza dependências que já existem no browser (CDN)
      external: ['marked'],
      // Banner com informação de geração
      banner: {
        js: `// Generated from TypeScript - DO NOT EDIT DIRECTLY\n// Source: ${path.relative(ROOT_DIR, entry.input)}\n// Built at: ${new Date().toISOString()}\n`,
      },
    });

    return true;
  } catch (error) {
    log(`  Error: ${error.message}`, 'red');
    return false;
  }
}

/**
 * Build completo
 */
async function build() {
  const startTime = Date.now();
  log('\n=== Portal PGE Frontend Build ===\n', 'cyan');

  const entryPoints = findEntryPoints();

  if (entryPoints.length === 0) {
    log('No TypeScript files found to compile.', 'yellow');
    log('Add .ts files to frontend/src/sistemas/<sistema>/ to get started.', 'yellow');
    return;
  }

  log(`Found ${entryPoints.length} file(s) to compile:\n`, 'blue');

  let successCount = 0;
  let failCount = 0;

  for (const entry of entryPoints) {
    const relativePath = path.relative(ROOT_DIR, entry.input);
    process.stdout.write(`  Building ${relativePath}... `);

    const success = await buildFile(entry);

    if (success) {
      successCount++;
      log('OK', 'green');
    } else {
      failCount++;
      log('FAILED', 'red');
    }
  }

  const elapsed = Date.now() - startTime;
  log(`\n=== Build Complete ===`, 'cyan');
  log(`Success: ${successCount}, Failed: ${failCount}`, failCount > 0 ? 'yellow' : 'green');
  log(`Time: ${elapsed}ms\n`, 'blue');

  if (failCount > 0) {
    process.exit(1);
  }
}

/**
 * Watch mode
 */
async function watch() {
  log('\n=== Portal PGE Frontend Watch Mode ===\n', 'cyan');
  log('Watching for changes in frontend/src/...\n', 'blue');

  // Build inicial
  await build();

  // Watch
  const entryPoints = findEntryPoints();

  for (const entry of entryPoints) {
    const ctx = await esbuild.context({
      entryPoints: [entry.input],
      outfile: entry.output,
      bundle: true,
      format: 'iife',
      target: ['es2020'],
      sourcemap: true,
      external: ['marked'],
      banner: {
        js: `// Generated from TypeScript - DO NOT EDIT DIRECTLY\n// Source: ${path.relative(ROOT_DIR, entry.input)}\n`,
      },
    });

    await ctx.watch();
    log(`  Watching: ${path.relative(ROOT_DIR, entry.input)}`, 'blue');
  }

  log('\nPress Ctrl+C to stop.\n', 'yellow');
}

// Main
const args = process.argv.slice(2);
if (args.includes('--watch')) {
  watch().catch(console.error);
} else {
  build().catch(console.error);
}
