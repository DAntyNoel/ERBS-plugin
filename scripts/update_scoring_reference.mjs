// Regenerate the independent oracle with Node 24 and an unmodified ERCraft checkout.
// Usage: node scripts/update_scoring_reference.mjs ERCraft-main ercraft-evidence
import { execFileSync } from 'node:child_process';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { registerHooks } from 'node:module';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const repo = pathToFileURL(resolve(process.argv[2]) + '/');
const evidence = resolve(process.argv[3]);
const commit = execFileSync('git', ['rev-parse', 'HEAD'], { cwd: repo, encoding: 'utf8' }).trim();
if (commit !== '93dd2a13345c53e5a6fb271c92d42b9fb62c7761') throw new Error('Unexpected source commit');
if (execFileSync('git', ['status', '--porcelain'], { cwd: repo, encoding: 'utf8' }).trim()) {
  throw new Error('Source checkout must be clean');
}
registerHooks({
  resolve(specifier, context, nextResolve) {
    if (context.parentURL?.startsWith(repo.href) && specifier.startsWith('.') && specifier.endsWith('.js')) {
      const candidate = new URL(specifier.slice(0, -3) + '.ts', context.parentURL);
      if (existsSync(candidate)) return nextResolve(candidate.href, context);
    }
    return nextResolve(specifier, context);
  },
});
const { computeMatchGradeV3 } = await import(new URL('backend/src/services/roleScore/roleScoreV3.ts', repo));
const { lookupCharacterWeaponRole } = await import(new URL('backend/src/services/characterPerformanceGrade/baselineStore.ts', repo));
const matches = [0, 1, 2, 3, 4].flatMap(page =>
  JSON.parse(readFileSync(resolve(evidence, `matches50-page${page}.json`))).data.items);
matches.push(...JSON.parse(readFileSync(resolve(evidence, 'role-sample-eva.json'))).data.items);
const rows = matches.filter(m => m.matchGradeScore != null).map(m => {
  const input = {
    tierKey: m.matchGradeBaselineTierKey, characterNum: m.characterNum, weaponTypeId: m.bestWeapon,
    role: lookupCharacterWeaponRole(m.characterNum, m.bestWeapon), placement: m.placement,
    durationSeconds: m.gameDuration, damageToPlayer: m.damageToPlayers, kills: m.kills,
    assists: m.assists, teamKills: m.teamKills, deaths: m.deaths,
    visionScore: m.visionScore, monsterKill: m.monsterKill,
  };
  const raw = {
    gameId: Number(m.matchId), seasonId: 41, matchingMode: 3, matchingTeamMode: 3,
    characterNum: m.characterNum, bestWeapon: m.bestWeapon, gameRank: m.placement,
    playTime: m.gameDuration, damageToPlayer: m.damageToPlayers, playerKill: m.kills,
    playerAssistant: m.assists, teamKill: m.teamKills, playerDeaths: m.deaths,
    viewContribution: m.visionScore, monsterKill: m.monsterKill, mmrAfter: m.rpAfter, mmrGain: m.rpDelta,
  };
  const expected = computeMatchGradeV3(input);
  if (expected.score !== m.matchGradeScore) throw new Error(`Online mismatch ${m.matchId}`);
  return { input, raw, onlineScore: m.matchGradeScore, expected };
});
const boundaries = [];
const roles = JSON.parse(readFileSync(new URL('backend/src/data/characterGrade/character-weapon-roles.v1.json', repo))).entries;
for (const role of new Set(Object.values(roles).map(e => e.role))) {
  const entry = Object.values(roles).find(e => e.role === role);
  for (const seconds of [null, 0, 479, 480, 540, 600, 899, 900, 1199, 1200, 1350, 1499, 1500, 1800, 2400]) {
    const input = { ...rows[0].input, tierKey: 'gold', characterNum: entry.characterNum,
      weaponTypeId: entry.weaponTypeId, role, durationSeconds: seconds };
    boundaries.push({ input, expected: computeMatchGradeV3(input) });
  }
}
for (const change of [
  { weaponTypeId: null }, { characterNum: 99999 }, { tierKey: 'absent' },
  { teamKills: 0 }, { deaths: 0 }, { damageToPlayer: null }, { placement: 0 },
  { damageToPlayer: null, kills: null, deaths: null, visionScore: null, monsterKill: null },
  { placement: 1, damageToPlayer: 999999, kills: 20, deaths: 0, visionScore: 100, monsterKill: 200 },
  { placement: 8, damageToPlayer: 999999, kills: 20, deaths: 0, visionScore: 100, monsterKill: 200 },
]) {
  const input = { ...rows[0].input, ...change };
  boundaries.push({ input, expected: computeMatchGradeV3(input) });
}
const target = new URL('../tests/fixtures/ercraft-scoring-reference.json', import.meta.url);
writeFileSync(target, JSON.stringify({ source: 'https://github.com/adgjmptw2/ERCraft-main', commit,
  method: 'Unmodified TypeScript core; raw fields and pre-match tier, no expected scores as inputs.',
  matches: rows, boundaries }, null, 2) + '\n');
console.log(`Generated ${rows.length} online-verified matches and ${boundaries.length} boundary cases`);

const { buildProductionAnalysisAxesForRows } = await import(new URL('backend/src/services/analysis/productionAnalysisAxes.ts', repo));
const { getRankTierFromRp } = await import(new URL('backend/src/utils/rankTier.ts', repo));
const axesCases = [];
function axesCase(name, selected, rp = 4445, scope = 'overall') {
  const rawRows = selected.map((raw, index) => ({
    gameId: String(raw.gameId ?? index), characterNum: raw.characterNum,
    gameMode: 'rank', placement: raw.gameRank, kills: raw.playerKill,
    assists: raw.playerAssistant, deaths: raw.playerDeaths, teamKills: raw.teamKill,
    damageToPlayer: raw.damageToPlayer, bestWeapon: raw.bestWeapon, gameDuration: raw.playTime,
    roleMetricsVersion: 1, viewContribution: raw.viewContribution, monsterKill: raw.monsterKill,
    victory: raw.gameRank === 1, displaySeasonId: 12,
  }));
  axesCases.push({ name, raw: selected, tierKey: rp < 3600 ? 'gold' : 'platinum', scope,
    expected: buildProductionAnalysisAxesForRows({ rows: rawRows,
      playerTier: getRankTierFromRp(rp, null, 12), displaySeasonId: 12, scope }) });
}
axesCase('empty', []);
axesCase('one-match', [rows[0].raw]);
axesCase('recent20', rows.slice(0, 20).map(c => c.raw));
axesCase('mixed-roles-215', rows.map(c => c.raw));
axesCase('zero-team-kills', rows.slice(0, 20).map(c => ({ ...c.raw, teamKill: 0 })));
axesCase('missing-vision', rows.slice(0, 20).map(c => ({ ...c.raw, viewContribution: null })));
axesCase('partial-monster', rows.slice(0, 20).map((c, i) => ({ ...c.raw, monsterKill: i % 2 ? null : c.raw.monsterKill })));
for (const count of [1, 2, 9, 10, 11, 20, 21]) {
  axesCase(`character-${count}`, rows.slice(0, count).map(c => c.raw), 4445, 'character');
}
const axesTarget = new URL('../tests/fixtures/ercraft-six-axis-reference.json', import.meta.url);
writeFileSync(axesTarget, JSON.stringify({ source: 'https://github.com/adgjmptw2/ERCraft-main',
  commit, version: 'production-analysis-axes.v1.1', cases: axesCases }, null, 2) + '\n');
console.log(`Generated ${axesCases.length} six-axis references from unmodified upstream exports`);
