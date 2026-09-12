package com.qiubo.optimaltv.data.repo

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class CatalogOriginPolicyTest {
    @Test
    fun `目录快照只接受豆瓣卡片`() {
        assertTrue(CatalogOriginPolicy.allows("douban", "douban:1292052"))
        assertFalse(CatalogOriginPolicy.allows("mcms", "mcms:12345"))
        assertFalse(CatalogOriginPolicy.allows("hhkan", "hhkan:12345"))
        assertFalse(CatalogOriginPolicy.allows("", "douban:1292052"))
    }
}
