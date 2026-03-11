import { describe, expect, it } from 'vitest';

import { getTranslations } from './i18n';

describe('model catalog translations', () => {
  it.each([
    ['en', 'Model Catalog', 'Save'],
    ['zh', '模型目录管理', '保存'],
    ['es', 'Catálogo de Modelos', 'Guardar'],
    ['fr', 'Catalogue de modèles', 'Enregistrer'],
    ['de', 'Modellkatalog', 'Speichern'],
    ['ja', 'モデルカタログ', '保存'],
    ['ko', '모델 카탈로그', '저장'],
  ] as const)('keeps %s model catalog texts aligned', (language, modelCatalogTitle, saveLabel) => {
    const t = getTranslations(language);

    expect(t.modelCatalogTitle).toBe(modelCatalogTitle);
    expect(t.execModeSave).toBe(saveLabel);
  });

  it.each([
    ['en', 'Catalog anomaly report not found'],
    ['zh', '未找到模型目录异常报告'],
    ['es', 'No se encontró el informe de anomalías del catálogo'],
    ['fr', 'Rapport d’anomalie du catalogue introuvable'],
    ['de', 'Anomaliebericht zum Modellkatalog nicht gefunden'],
    ['ja', 'カタログ異常レポートが見つかりません'],
    ['ko', '카탈로그 이상 보고서를 찾을 수 없습니다'],
  ] as const)('keeps %s model catalog error texts aligned', (language, errorText) => {
    const t = getTranslations(language);

    expect(t.code_MODEL_CATALOG_ANOMALY_REPORT_NOT_FOUND).toBe(errorText);
  });
});
