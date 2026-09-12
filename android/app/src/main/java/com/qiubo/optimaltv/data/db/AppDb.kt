package com.qiubo.optimaltv.data.db

import android.content.Context
import androidx.room.Dao
import androidx.room.Database
import androidx.room.Entity
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.PrimaryKey
import androidx.room.Query
import androidx.room.Room
import androidx.room.RoomDatabase
import kotlinx.coroutines.flow.Flow

/** 收藏表（技术方案 §3.5） */
@Entity(tableName = "favorite")
data class FavoriteEntity(
    @PrimaryKey val vodId: String,
    val title: String,
    val posterUrl: String,
    val createdAt: Long,
)

/** 观看历史表 */
@Entity(tableName = "history")
data class HistoryEntity(
    @PrimaryKey val vodId: String,
    val title: String,
    val posterUrl: String,
    val epIndex: Int,
    val positionMs: Long,
    val durationMs: Long,
    val updatedAt: Long,
)

/** 播放进度表：vodKey = 多集 "{vodId}-e{n}"，单集 "{vodId}" */
@Entity(tableName = "progress")
data class ProgressEntity(
    @PrimaryKey val vodKey: String,
    val vodId: String,
    val epIndex: Int,
    val positionMs: Long,
    val durationMs: Long,
    val updatedAt: Long,
)

@Dao
interface VodDao {

    // ---- favorite ----
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun addFavorite(item: FavoriteEntity)

    @Query("DELETE FROM favorite WHERE vodId = :vodId")
    suspend fun removeFavorite(vodId: String)

    @Query("SELECT * FROM favorite ORDER BY createdAt DESC")
    fun favoritesFlow(): Flow<List<FavoriteEntity>>

    @Query("SELECT EXISTS(SELECT 1 FROM favorite WHERE vodId = :vodId)")
    fun isFavoriteFlow(vodId: String): Flow<Boolean>

    @Query("DELETE FROM favorite")
    suspend fun clearFavorites()

    // ---- history ----
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertHistory(item: HistoryEntity)

    @Query("SELECT * FROM history ORDER BY updatedAt DESC LIMIT :limit")
    fun historyFlow(limit: Int = 30): Flow<List<HistoryEntity>>

    @Query("SELECT * FROM history WHERE vodId = :vodId LIMIT 1")
    suspend fun getHistory(vodId: String): HistoryEntity?

    @Query("DELETE FROM history")
    suspend fun clearHistory()

    // ---- progress ----
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertProgress(item: ProgressEntity)

    @Query("SELECT * FROM progress WHERE vodKey = :vodKey LIMIT 1")
    suspend fun getProgress(vodKey: String): ProgressEntity?

    /** 该影片全部线路/集的进度（详情页续播判定批量取数：旧版逐集 getProgress 串行上千次） */
    @Query("SELECT * FROM progress WHERE vodId = :vodId")
    suspend fun progressOfVod(vodId: String): List<ProgressEntity>

    @Query("DELETE FROM progress WHERE vodId = :vodId")
    suspend fun clearProgressOfVod(vodId: String)

    @Query("DELETE FROM progress")
    suspend fun clearAllProgress()
}

@Database(
    entities = [FavoriteEntity::class, HistoryEntity::class, ProgressEntity::class],
    version = 1,
    exportSchema = false,
)
abstract class AppDb : RoomDatabase() {
    abstract fun vodDao(): VodDao

    companion object {
        @Volatile private var instance: AppDb? = null

        fun get(context: Context): AppDb = instance ?: synchronized(this) {
            instance ?: Room.databaseBuilder(context.applicationContext, AppDb::class.java, "optimal_tv.db")
                .fallbackToDestructiveMigration()
                .build()
                .also { instance = it }
        }
    }
}
