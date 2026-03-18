import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { ClubRepoJson } from '../services/club-repo-json.js';

function createRepo(): ClubRepoJson {
  const dir = mkdtempSync(join(tmpdir(), 'cardpilot-wallet-'));
  return new ClubRepoJson(join(dir, 'clubs.json'));
}

describe('Club wallet ledger', () => {
  it('balance equals SUM(ledger amounts) for a user', async () => {
    const repo = createRepo();
    const clubId = 'club-1';
    const userId = 'user-1';

    await repo.appendWalletTx({
      clubId,
      userId,
      type: 'deposit',
      amount: 1_000,
      createdBy: 'admin-1',
    });
    await repo.appendWalletTx({ clubId, userId, type: 'buy_in', amount: -250, createdBy: userId });
    await repo.appendWalletTx({ clubId, userId, type: 'cash_out', amount: 300, createdBy: userId });
    await repo.appendWalletTx({
      clubId,
      userId,
      type: 'adjustment',
      amount: -50,
      createdBy: 'admin-1',
    });

    const ledger = await repo.listWalletTxs(clubId, userId, 'chips', 100, 0);
    const sum = ledger.reduce((acc, tx) => acc + tx.amount, 0);
    const balance = await repo.getWalletBalance(clubId, userId, 'chips');
    assert.equal(balance, sum);
  });

  it('deposit -> buy-in -> cash-out keeps balance correct', async () => {
    const repo = createRepo();
    const clubId = 'club-2';
    const userId = 'user-2';

    const d1 = await repo.appendWalletTx({
      clubId,
      userId,
      type: 'deposit',
      amount: 2_000,
      createdBy: 'admin-1',
    });
    assert.ok(d1);
    assert.equal(d1!.newBalance, 2_000);

    const b1 = await repo.appendWalletTx({
      clubId,
      userId,
      type: 'buy_in',
      amount: -600,
      createdBy: userId,
      refType: 'table_seat',
      refId: 'tbl-a:3',
    });
    assert.ok(b1);
    assert.equal(b1!.newBalance, 1_400);

    const c1 = await repo.appendWalletTx({
      clubId,
      userId,
      type: 'cash_out',
      amount: 850,
      createdBy: userId,
      refType: 'table_seat',
      refId: 'tbl-a:3',
    });
    assert.ok(c1);
    assert.equal(c1!.newBalance, 2_250);

    const finalBalance = await repo.getWalletBalance(clubId, userId, 'chips');
    assert.equal(finalBalance, 2_250);
  });
});
