package de.s42.swapmyaxe.config;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import net.fabricmc.loader.api.FabricLoader;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class Config {

    private static final Logger LOGGER = LoggerFactory.getLogger("swapmyaxe");
    private static final Gson GSON = new GsonBuilder().setPrettyPrinting().create();
    private static final Path CONFIG_PATH =
            FabricLoader.getInstance().getConfigDir().resolve("swapmyaxe.json");

    public SwapMode swapMode = SwapMode.SLOT;
    public int targetSlot = 1;
    public String targetItem = "minecraft:diamond_sword";
    public boolean enabled = true;
    public boolean doubleHit = true;
    public int swapDelayTicks = 0;
    public boolean restoreToAxe = false;

    public static Config load() {
        if (Files.exists(CONFIG_PATH)) {
            try {
                String json = Files.readString(CONFIG_PATH);
                Config config = GSON.fromJson(json, Config.class);
                if (config != null) {
                    config.sanitize();
                    return config;
                }
                LOGGER.warn("[SwapMyAxe] Config file was empty/null; restoring defaults.");
            } catch (IOException | RuntimeException e) {
                LOGGER.warn("[SwapMyAxe] Failed to read config; restoring defaults.", e);
            }
        }

        Config defaults = new Config();
        defaults.save();
        return defaults;
    }

    public void save() {
        sanitize();
        try {
            Files.createDirectories(CONFIG_PATH.getParent());
            Files.writeString(CONFIG_PATH, GSON.toJson(this));
        } catch (IOException e) {
            LOGGER.warn("[SwapMyAxe] Failed to save config.", e);
        }
    }

    private void sanitize() {
        if (swapMode == null) {
            swapMode = SwapMode.SLOT;
        }
        targetSlot = Math.max(0, Math.min(8, targetSlot));
        swapDelayTicks = Math.max(0, Math.min(20, swapDelayTicks));
        if (targetItem == null || targetItem.isBlank()) {
            targetItem = "minecraft:diamond_sword";
        }
    }

    public enum SwapMode {
        SLOT,
        ITEM
    }
}
