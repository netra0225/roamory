package de.s42.swapmyaxe;

import com.mojang.blaze3d.platform.InputConstants;
import de.s42.swapmyaxe.config.Config;
import de.s42.swapmyaxe.handler.SwapHandler;
import net.fabricmc.api.ModInitializer;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientTickEvents;
import net.fabricmc.fabric.api.client.keybinding.v1.KeyBindingHelper;
import net.minecraft.client.KeyMapping;
import net.minecraft.client.Minecraft;
import net.minecraft.resources.ResourceLocation;
import org.lwjgl.glfw.GLFW;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class SwapMyAxe implements ModInitializer {

    public static final String MOD_ID = "swapmyaxe";
    public static final Logger LOGGER = LoggerFactory.getLogger(MOD_ID);
    public static Config CONFIG;
    private static KeyMapping toggleKey;
    private static boolean wasPressed = false;

    @Override
    public void onInitialize() {
        CONFIG = Config.load();

        toggleKey = KeyBindingHelper.registerKeyBinding(new KeyMapping(
                "key.sma.toggle",
                InputConstants.Type.KEYSYM,
                GLFW.GLFW_KEY_V,
                KeyMapping.Category.register(ResourceLocation.parse("category.sma"))
        ));

        ClientTickEvents.END_CLIENT_TICK.register(this::handleKey);
        SwapHandler.register();
        LOGGER.info("SwapMyAxe initialized for Minecraft 1.21.11.");
    }

    private void handleKey(Minecraft client) {
        if (client == null || client.player == null || CONFIG == null) {
            return;
        }

        boolean pressed = toggleKey.isDown();
        if (pressed && !wasPressed) {
            CONFIG.enabled = !CONFIG.enabled;
            CONFIG.save();
            wasPressed = true;
        } else if (!pressed) {
            wasPressed = false;
        }
    }
}
